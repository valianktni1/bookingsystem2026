"""V8.49 SMS centre routes, automations and The SMS Works webhooks."""

from __future__ import annotations

import base64
import hmac
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .business_time import (automatic_delivery_allowed, automatic_delivery_window_label,
                            business_date, business_today)
from .config import get_settings
from .database import SessionLocal, get_db
from .models import (Admin, Booking, Brand, BusinessProfile, Client, EmailLog, Invoice,
                     Quote, RecordKind, RecordStatus, SmsMessage, SmsTemplate, Task)
from .payment_arrangements import active_payment_arrangement, arrangement_json
from .security import current_admin
from .services import audit
from .sms_service import (SMS_AUTOMATION_LABELS, normalise_sms_number, render_sms_template,
                          send_booking_sms, sms_message_json, sms_parts, sms_ready, sms_sender)


settings = get_settings()


class SmsSendIn(BaseModel):
    body: str = Field(min_length=1, max_length=1280)
    template_key: str | None = Field(default=None, max_length=80)
    confirmed: bool = False


class SmsTemplatePatchIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=140)
    body: str | None = Field(default=None, min_length=1, max_length=1280)
    is_active: bool | None = None


class SmsAutomationControlIn(BaseModel):
    paused: bool


def sms_automation_paused(booking: Booking, template_key: str) -> bool:
    controls = dict((booking.workflow_state or {}).get("sms_automation_controls") or {})
    return bool((controls.get(template_key) or {}).get("paused"))


def sms_status_json(db: Session | None = None) -> dict[str, Any]:
    reply_capable = bool(settings.sms_reply_number)
    try:
        sender = sms_sender()
        sender_error = None
    except ValueError as exc:
        sender = settings.sms_reply_number or settings.sms_sender_id
        sender_error = str(exc)
    unmatched = 0
    if db is not None:
        unmatched = len(db.scalars(select(SmsMessage.id).where(
            SmsMessage.direction == "incoming", SmsMessage.booking_id.is_(None)
        )).all())
    return {
        "provider": "The SMS Works",
        "enabled": settings.sms_enabled,
        "configured": bool(settings.sms_api_token),
        "ready": sms_ready(),
        "automatic_enabled": settings.sms_automatic_enabled,
        "automatic_window_open": automatic_delivery_allowed(
            settings.automatic_message_start_hour,
            settings.automatic_message_end_hour,
        ),
        "automatic_window": automatic_delivery_window_label(
            settings.automatic_message_start_hour,
            settings.automatic_message_end_hour,
        ),
        "sender": sender,
        "sender_error": sender_error,
        "sender_mode": "reply_number" if reply_capable else "brand_name",
        "reply_capable": reply_capable,
        "test_number_configured": bool(settings.sms_test_number),
        "webhook_secured": bool(settings.sms_webhook_username and settings.sms_webhook_password),
        "delivery_webhook_url": f"{settings.app_url.rstrip('/')}/api/integrations/smsworks/delivery",
        "incoming_webhook_url": f"{settings.app_url.rstrip('/')}/api/integrations/smsworks/incoming",
        "unmatched_replies": unmatched,
    }


def _booking_for_sms(db: Session, booking_id: str) -> Booking:
    booking = db.scalar(select(Booking).options(
        selectinload(Booking.client), selectinload(Booking.invoices), selectinload(Booking.quotes)
    ).where(Booking.id == booking_id))
    if not booking:
        raise HTTPException(404, "Record not found")
    return booking


def _template_json(template: SmsTemplate, booking: Booking | None = None,
                   profile: BusinessProfile | None = None) -> dict[str, Any]:
    body = template.body
    if booking is not None and profile is not None:
        body = render_sms_template(template, booking, profile)
    return {
        "id": template.id,
        "brand": template.brand.value,
        "template_key": template.template_key,
        "display_name": template.display_name,
        "body": template.body,
        "rendered_body": body,
        "is_automatic": template.is_automatic,
        "is_active": template.is_active,
        "estimate": sms_parts(body),
    }


def _due_sms_automations(db: Session, booking: Booking,
                         today: date) -> list[tuple[str, date]]:
    """Return independent SMS dates without changing the email journey."""
    if (booking.legacy_source or booking.automation_suppressed
            or booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING):
        return []
    due: list[tuple[str, date]] = []
    accepted = next((quote for quote in booking.quotes if quote.status == "accepted"), None)
    if not accepted and booking.status in (RecordStatus.ENQUIRY, RecordStatus.QUOTED):
        quote_sent_at = db.scalar(select(EmailLog.sent_at).where(
            EmailLog.booking_id == booking.id,
            EmailLog.template_key == "quote",
            EmailLog.status == "sent",
        ).order_by(EmailLog.sent_at.desc()).limit(1))
        if quote_sent_at:
            quote_sent_date = business_date(quote_sent_at)
            days_since = (today - quote_sent_date).days
            if 1 <= days_since < 9 and not sms_automation_paused(booking, "quote_followup_1"):
                due.append(("quote_followup_1", quote_sent_date + timedelta(days=1)))
            elif 9 <= days_since <= 16 and not sms_automation_paused(booking, "quote_followup_final"):
                due.append(("quote_followup_final", quote_sent_date + timedelta(days=9)))
    if accepted and not active_payment_arrangement(booking):
        invoice = next((item for item in booking.invoices if item.id == accepted.invoice_id), None)
        if (invoice and invoice.status not in ("void", "cancelled")
                and Decimal(str(invoice.paid or 0)) <= 0
                and invoice.deposit_due_date and invoice.deposit_due_date <= today
                and (today - invoice.deposit_due_date).days <= 7
                and not sms_automation_paused(booking, "deposit_due_1")):
            due.append(("deposit_due_1", invoice.deposit_due_date))
    if booking.event_date and booking.status in (RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS):
        days_to_wedding = (booking.event_date - today).days
        if 113 <= days_to_wedding <= 120 and not sms_automation_paused(booking, "check_in_120"):
            due.append(("check_in_120", booking.event_date - timedelta(days=120)))
        elif 23 <= days_to_wedding <= 30 and not sms_automation_paused(booking, "check_in_30"):
            due.append(("check_in_30", booking.event_date - timedelta(days=30)))
    has_balance = any(
        invoice.status not in ("void", "cancelled")
        and Decimal(str(invoice.paid or 0)) < Decimal(str(invoice.total or 0))
        for invoice in booking.invoices
    )
    arrangement = arrangement_json(booking)
    payment_paused = bool(arrangement and arrangement["active"] and arrangement["pause_payment_reminders"])
    if booking.balance_due_date and has_balance and not payment_paused:
        days_to_balance = (booking.balance_due_date - today).days
        if 2 <= days_to_balance <= 7 and not sms_automation_paused(booking, "balance_due_7"):
            due.append(("balance_due_7", booking.balance_due_date - timedelta(days=7)))
        elif 0 <= days_to_balance <= 1 and not sms_automation_paused(booking, "balance_due_1"):
            due.append(("balance_due_1", booking.balance_due_date - timedelta(days=1)))
    return due


def run_due_sms_automations(db: Session, *, today: date | None = None) -> dict[str, int | bool]:
    if not settings.sms_automatic_enabled or not sms_ready():
        return {"enabled": False, "sent": 0, "skipped": 0, "failed": 0}
    check_date = today or business_today()
    sent = skipped = failed = 0
    bookings = db.scalars(select(Booking).options(
        selectinload(Booking.client), selectinload(Booking.invoices), selectinload(Booking.quotes)
    ).where(Booking.archived_at.is_(None), Booking.status != RecordStatus.CANCELLED)).all()
    profiles = {row.brand: row for row in db.scalars(select(BusinessProfile)).all()}
    templates = {
        row.template_key: row for row in db.scalars(select(SmsTemplate).where(
            SmsTemplate.brand == Brand.WBM,
            SmsTemplate.is_automatic.is_(True),
            SmsTemplate.is_active.is_(True),
        )).all()
    }
    for booking in bookings:
        for template_key, scheduled_for in _due_sms_automations(db, booking, check_date):
            template = templates.get(template_key)
            profile = profiles.get(booking.brand)
            if not template or not profile:
                skipped += 1
                continue
            dedupe_key = f"{booking.id}:{template_key}:{scheduled_for.isoformat()}"
            existing = db.scalar(select(SmsMessage).where(SmsMessage.dedupe_key == dedupe_key))
            if existing:
                skipped += 1
                continue
            body = render_sms_template(template, booking, profile)
            try:
                _row, ok = send_booking_sms(
                    db, booking, body, template_key=template_key,
                    automated=True, dedupe_key=dedupe_key,
                )
            except ValueError as exc:
                audit(db, "automatic_sms_blocked", "booking", booking.id, {
                    "template": template_key, "error": str(exc)[:500],
                })
                db.commit()
                failed += 1
                continue
            if ok:
                sent += 1
            else:
                failed += 1
    return {"enabled": True, "sent": sent, "skipped": skipped, "failed": failed}


async def sms_automation_loop() -> None:
    import asyncio

    while True:
        await asyncio.sleep(settings.sms_scan_hours * 3600)
        within_window = automatic_delivery_allowed(
            settings.automatic_message_start_hour,
            settings.automatic_message_end_hour,
        )
        if settings.sms_automatic_enabled and sms_ready() and within_window:
            with SessionLocal() as db:
                await asyncio.to_thread(run_due_sms_automations, db, today=business_today())


def _verify_webhook(request: Request) -> None:
    expected_user = settings.sms_webhook_username or ""
    expected_password = settings.sms_webhook_password or ""
    if not expected_user or not expected_password:
        raise HTTPException(503, "SMS webhook authentication is not configured")
    auth = request.headers.get("authorization", "")
    supplied_user = supplied_password = ""
    if auth.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth.split(" ", 1)[1], validate=True).decode("utf-8")
            supplied_user, supplied_password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            pass
    valid = hmac.compare_digest(supplied_user, expected_user) & hmac.compare_digest(
        supplied_password, expected_password
    )
    if not valid:
        raise HTTPException(401, "Webhook authentication failed", headers={"WWW-Authenticate": "Basic"})


def _metadata_dict(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    if isinstance(raw, list):
        result = {}
        for item in raw:
            if isinstance(item, dict) and item.get("key") is not None:
                result[str(item["key"])] = str(item.get("value", ""))
        return result
    return {}


def _match_incoming_booking(db: Session, payload: dict[str, Any]) -> Booking | None:
    metadata = _metadata_dict(payload.get("metadata"))
    if metadata.get("booking_id"):
        booking = db.get(Booking, metadata["booking_id"])
        if booking:
            return booking
    outbound_id = str(payload.get("outboundmessageid") or "")
    if outbound_id:
        outgoing = db.scalar(select(SmsMessage).where(
            SmsMessage.provider_message_id == outbound_id
        ))
        if outgoing and outgoing.booking_id:
            booking = db.get(Booking, outgoing.booking_id)
            if booking:
                return booking
    try:
        source = normalise_sms_number(str(payload.get("from") or ""))
    except ValueError:
        return None
    recent = db.scalars(select(Booking).options(selectinload(Booking.client)).where(
        Booking.archived_at.is_(None)
    ).order_by(Booking.updated_at.desc())).all()
    for booking in recent:
        try:
            if normalise_sms_number(booking.client.phone) == source:
                return booking
        except ValueError:
            continue
    return None


def register_sms_routes(app: FastAPI) -> None:
    @app.get("/api/sms/status")
    def get_sms_status(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
        return sms_status_json(db)

    @app.get("/api/sms/templates")
    def list_sms_templates(
        brand: Brand | None = Query(None),
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        stmt = select(SmsTemplate).order_by(SmsTemplate.is_automatic.desc(), SmsTemplate.display_name)
        if brand:
            stmt = stmt.where(SmsTemplate.brand == brand)
        return {"status": sms_status_json(db), "templates": [
            _template_json(row) for row in db.scalars(stmt).all()
        ]}

    @app.patch("/api/sms/templates/{template_id}")
    def patch_sms_template(
        template_id: str,
        payload: SmsTemplatePatchIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        row = db.get(SmsTemplate, template_id)
        if not row:
            raise HTTPException(404, "SMS template not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        estimate = sms_parts(row.body)
        audit(db, "update_sms_template", "sms_template", row.id, {
            "template_key": row.template_key,
            "active": row.is_active,
            "parts": estimate["parts"],
            "admin": admin.email,
        })
        db.commit()
        return _template_json(row)

    @app.get("/api/bookings/{booking_id}/sms")
    def booking_sms_centre(
        booking_id: str,
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = _booking_for_sms(db, booking_id)
        profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
        templates = db.scalars(select(SmsTemplate).where(
            SmsTemplate.brand == booking.brand
        ).order_by(SmsTemplate.is_automatic, SmsTemplate.display_name)).all()
        messages = db.scalars(select(SmsMessage).where(
            SmsMessage.booking_id == booking.id
        ).order_by(SmsMessage.created_at.desc()).limit(100)).all()
        controls = []
        template_by_key = {row.template_key: row for row in templates}
        for key, label in SMS_AUTOMATION_LABELS.items():
            template = template_by_key.get(key)
            controls.append({
                "template_key": key,
                "label": label,
                "paused": sms_automation_paused(booking, key),
                "active": bool(template and template.is_active),
                "available": bool(template),
            })
        phone = None
        phone_error = None
        try:
            phone = normalise_sms_number(booking.client.phone)
        except ValueError as exc:
            phone_error = str(exc)
        return {
            "status": sms_status_json(db),
            "booking_id": booking.id,
            "client_name": booking.title,
            "client_phone": booking.client.phone,
            "normalised_phone": phone,
            "phone_error": phone_error,
            "is_test": booking.is_test,
            "legacy_manual_only": bool(booking.legacy_source),
            "templates": [_template_json(row, booking, profile) for row in templates if profile],
            "automations": controls,
            "messages": [sms_message_json(row) for row in messages],
        }

    @app.post("/api/bookings/{booking_id}/sms/send", status_code=201)
    def send_sms_now(
        booking_id: str,
        payload: SmsSendIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        if not payload.confirmed:
            raise HTTPException(422, "Confirm that you have checked the number and exact message")
        if not sms_ready():
            raise HTTPException(503, "SMS is off. Add The SMS Works token and set SMS_ENABLED=true first")
        booking = _booking_for_sms(db, booking_id)
        if booking.status == RecordStatus.CANCELLED:
            raise HTTPException(409, "Cancelled bookings cannot be texted")
        try:
            row, ok = send_booking_sms(
                db, booking, payload.body,
                template_key=payload.template_key,
                automated=False,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not ok:
            raise HTTPException(503, row.error or "The text could not be sent")
        audit(db, "admin_confirmed_sms", "booking", booking.id, {
            "sms_message_id": row.id, "admin": admin.email,
        })
        db.commit()
        return {"ok": True, "message": sms_message_json(row)}

    @app.put("/api/bookings/{booking_id}/sms/automations/{template_key}")
    def control_sms_automation(
        booking_id: str,
        template_key: Literal[
            "quote_followup_1", "quote_followup_final", "deposit_due_1",
            "check_in_120", "check_in_30", "balance_due_7", "balance_due_1",
        ],
        payload: SmsAutomationControlIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = db.get(Booking, booking_id)
        if not booking:
            raise HTTPException(404, "Record not found")
        workflow = dict(booking.workflow_state or {})
        controls = dict(workflow.get("sms_automation_controls") or {})
        controls[template_key] = {
            "paused": payload.paused,
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "changed_by": admin.email,
        }
        workflow["sms_automation_controls"] = controls
        booking.workflow_state = workflow
        audit(db, "pause_sms_automation" if payload.paused else "resume_sms_automation",
              "booking", booking.id, {
                  "template_key": template_key,
                  "label": SMS_AUTOMATION_LABELS[template_key],
                  "admin": admin.email,
              })
        db.commit()
        return {"ok": True, "template_key": template_key, "paused": payload.paused,
                "message": f"{SMS_AUTOMATION_LABELS[template_key]} {'paused' if payload.paused else 'resumed'}"}

    @app.post("/api/sms/automations/run")
    def run_sms_now(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
        if not settings.sms_automatic_enabled:
            raise HTTPException(409, "Automatic SMS is switched off")
        if not sms_ready():
            raise HTTPException(503, "SMS is not fully configured")
        return run_due_sms_automations(db)

    @app.post("/api/integrations/smsworks/delivery")
    async def sms_delivery_webhook(request: Request, db: Session = Depends(get_db)):
        _verify_webhook(request)
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(400, "Invalid JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(400, "Invalid delivery report")
        provider_id = str(payload.get("messageid") or "")
        row = db.scalar(select(SmsMessage).where(SmsMessage.provider_message_id == provider_id))
        if not row:
            return {"ok": True, "matched": False}
        provider_status = str(payload.get("status") or "").upper()
        status_map = {
            "SCHEDULED": "scheduled", "SENT": "sent", "DELIVERED": "delivered",
            "UNDELIVERABLE": "undeliverable", "UNDELIVERED": "undeliverable",
            "EXPIRED": "expired", "REJECTED": "rejected",
        }
        if provider_status in status_map:
            row.status = status_map[provider_status]
        if row.status == "delivered" and not row.delivered_at:
            row.delivered_at = datetime.now(timezone.utc)
        failure = payload.get("failurereason") if isinstance(payload.get("failurereason"), dict) else {}
        if row.status in {"undeliverable", "expired", "rejected"}:
            row.error = str(failure.get("details") or f"Delivery status: {provider_status}")[:2000]
            if row.booking_id and not db.scalar(select(Task.id).where(
                Task.booking_id == row.booking_id,
                Task.workflow_key == f"sms_delivery:{row.id}",
            ).limit(1)):
                db.add(Task(
                    booking_id=row.booking_id,
                    title="Check mobile number - a text was not delivered",
                    workflow_key=f"sms_delivery:{row.id}",
                    due_at=datetime.now(timezone.utc),
                ))
        row.parts = int(payload.get("messageparts") or row.parts or 1)
        row.provider_data = {**(row.provider_data or {}), "delivery": payload}
        audit(db, "sms_delivery_update", "booking", row.booking_id, {
            "sms_message_id": row.id, "status": row.status,
        })
        db.commit()
        return {"ok": True, "matched": True}

    @app.post("/api/integrations/smsworks/incoming")
    async def sms_incoming_webhook(request: Request, db: Session = Depends(get_db)):
        _verify_webhook(request)
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(400, "Invalid JSON") from exc
        if not isinstance(payload, dict) or str(payload.get("messagetype") or "").lower() != "incoming":
            raise HTTPException(400, "Invalid incoming SMS")
        provider_id = str(payload.get("messageid") or "")
        if not provider_id:
            raise HTTPException(400, "Incoming SMS is missing its message ID")
        existing = db.scalar(select(SmsMessage).where(SmsMessage.provider_message_id == provider_id))
        if existing:
            return {"ok": True, "duplicate": True, "matched": bool(existing.booking_id)}
        booking = _match_incoming_booking(db, payload)
        try:
            sender = normalise_sms_number(str(payload.get("from") or ""))
        except ValueError:
            sender = str(payload.get("from") or "")[:30]
        row = SmsMessage(
            booking_id=booking.id if booking else None,
            brand=booking.brand if booking else Brand.WBM,
            direction="incoming",
            sender=sender,
            recipient=str(payload.get("to") or "")[:30] or None,
            body=str(payload.get("content") or "").strip()[:1280],
            status="received",
            provider_message_id=provider_id,
            parts=int(payload.get("parts") or 1),
            automated=False,
            received_at=datetime.now(timezone.utc),
            provider_data={"incoming": payload},
        )
        db.add(row)
        db.flush()
        if booking and booking.status != RecordStatus.CANCELLED:
            db.add(Task(
                booking_id=booking.id,
                title=f"Reply to {booking.title}'s text message",
                workflow_key=f"sms_reply:{provider_id}"[:100],
                due_at=datetime.now(timezone.utc),
            ))
        audit(db, "receive_sms", "booking", booking.id if booking else None, {
            "sms_message_id": row.id,
            "matched": bool(booking),
        })
        db.commit()
        return {"ok": True, "duplicate": False, "matched": bool(booking)}

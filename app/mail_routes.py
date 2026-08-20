"""Admin-only unified inbox and manual threaded reply endpoints."""

from __future__ import annotations

import hashlib
import re
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import get_db
from .email_service import send_email_message, smtp_ready
from .mail_service import (append_to_sent, build_reply_message, friendly_mail_error,
                           imap_credentials, imap_ready, list_inbox_messages,
                           list_correspondent_messages, mailbox_status, read_attachment,
                           read_inbox_message, list_sent_messages_to_correspondent, set_seen)
from .models import (Admin, AuditLog, Booking, Brand, BusinessProfile, Client,
                     ClientPortalToken, EmailLog, FormSubmission, MailboxReply,
                     RecordStatus)
from .security import current_admin
from .services import audit


class MailSeenIn(BaseModel):
    seen: bool


class MailReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    booking_id: str | None = Field(default=None, min_length=36, max_length=36)
    include_account_link: bool = True


def _brand(value: str) -> Brand:
    try:
        return Brand(value)
    except ValueError:
        raise HTTPException(404, "Mailbox not found")


def _booking_match(db: Session, email: str, brand: Brand) -> Booking | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    rows = db.scalars(select(Booking).options(selectinload(Booking.client)).join(Client).where(
        Booking.brand == brand,
        func.lower(Client.email) == email,
    )).all()
    if not rows:
        return None

    def priority(item: Booking):
        cancelled = item.status == RecordStatus.CANCELLED
        past = bool(item.event_date and item.event_date < date.today())
        distance = abs((item.event_date - date.today()).days) if item.event_date else 999_999
        return cancelled, past, distance, item.created_at

    return sorted(rows, key=priority)[0]


def _booking_matches(db: Session, emails: set[str], brand: Brand) -> dict[str, Booking]:
    wanted = {email.strip().lower() for email in emails if email and email.strip()}
    if not wanted:
        return {}
    rows = db.scalars(select(Booking).options(selectinload(Booking.client)).join(Client).where(
        Booking.brand == brand,
        func.lower(Client.email).in_(wanted),
    )).all()
    grouped: dict[str, list[Booking]] = {}
    for row in rows:
        grouped.setdefault(row.client.email.lower(), []).append(row)

    def priority(item: Booking):
        cancelled = item.status == RecordStatus.CANCELLED
        past = bool(item.event_date and item.event_date < date.today())
        distance = abs((item.event_date - date.today()).days) if item.event_date else 999_999
        return cancelled, past, distance, item.created_at

    return {email: sorted(items, key=priority)[0] for email, items in grouped.items()}


def _booking_json(item: Booking | None) -> dict | None:
    if not item:
        return None
    return {
        "id": item.id,
        "title": item.title,
        "brand": item.brand.value,
        "kind": item.kind.value,
        "status": item.status.value,
        "event_date": item.event_date.isoformat() if item.event_date else None,
        "legacy_source": item.legacy_source,
        "automation_suppressed": item.automation_suppressed,
        "client_email": item.client.email,
    }


def _thread_replies(db: Session, brand: Brand, recipient: str, message_id: str) -> list[dict]:
    thread_condition = (
        or_(MailboxReply.in_reply_to == message_id,
            MailboxReply.thread_references.contains(message_id))
        if message_id else func.lower(MailboxReply.recipient) == recipient.lower()
    )
    rows = db.scalars(select(MailboxReply).where(
        MailboxReply.brand == brand, thread_condition,
    ).order_by(MailboxReply.sent_at.desc()).limit(30)).all()
    return [{
        "id": row.id,
        "recipient": row.recipient,
        "subject": row.subject,
        "body": row.body,
        "message_id": row.message_id,
        "sent_at": row.sent_at.isoformat(),
        "copied_to_sent": row.copied_to_sent,
        "status": row.status,
    } for row in reversed(rows)]


def _new_portal_url(db: Session, booking: Booking) -> str | None:
    if booking.legacy_source == "studio_ninja" or booking.status == RecordStatus.CANCELLED:
        return None
    raw = secrets.token_urlsafe(32)
    lifetime = 365
    if booking.event_date:
        lifetime = min(3650, max(365, (booking.event_date - date.today()).days + 365))
    row = ClientPortalToken(
        booking_id=booking.id,
        token_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=lifetime),
    )
    db.add(row)
    return f"{get_settings().app_url.rstrip('/')}/client/{raw}"


def register_mail_routes(app: FastAPI) -> None:
    @app.get("/api/mail/status")
    def mail_status(_: Admin = Depends(current_admin)):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(mailbox_status, brand): brand for brand in Brand}
            results = []
            for future in as_completed(futures):
                brand = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    username, _ = imap_credentials(brand)
                    results.append({"brand": brand.value, "address": username,
                                    "configured": imap_ready(brand), "connected": False,
                                    "total": 0, "unread": 0,
                                    "error": friendly_mail_error(exc)})
        results.sort(key=lambda item: item["brand"], reverse=True)
        return {"accounts": results, "unread": sum(item["unread"] for item in results)}

    @app.get("/api/mail/messages")
    def mail_messages(
        brand: Brand | None = None,
        unread_only: bool = False,
        limit: int = Query(default=60, ge=10, le=200),
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        brands = [brand] if brand else list(Brand)

        def load(mail_brand: Brand):
            if not imap_ready(mail_brand):
                return mail_brand, [], "Mailbox not configured"
            try:
                return mail_brand, list_inbox_messages(mail_brand, limit, unread_only), None
            except Exception as exc:
                return mail_brand, [], friendly_mail_error(exc)

        results: list[tuple[Brand, list[dict], str | None]] = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(load, item) for item in brands]
            results = [future.result() for future in as_completed(futures)]
        messages: list[dict] = []
        errors: dict[str, str] = {}
        for mail_brand, rows, error in results:
            if error:
                errors[mail_brand.value] = error
            matches = _booking_matches(
                db, {row["reply_to_email"] for row in rows}, mail_brand
            )
            for row in rows:
                row["booking"] = _booking_json(matches.get(row["reply_to_email"].lower()))
                messages.append(row)
        messages.sort(key=lambda item: (item.get("date") or "", int(item["uid"])), reverse=True)
        return {"messages": messages[:limit], "errors": errors,
                "configured": {item.value: imap_ready(item) for item in Brand}}

    @app.get("/api/bookings/{booking_id}/conversation")
    def booking_conversation(
        booking_id: str,
        limit: int = Query(default=60, ge=10, le=100),
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        """Return only mail securely associated with this booking and client."""
        booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(
            Booking.id == booking_id
        ))
        if not booking:
            raise HTTPException(404, "Booking not found")

        # The primary address is taken from the client record. Once the couple
        # have submitted their booking form, include both exact addresses from
        # that form as well. No name, subject or partial-address matching is
        # used here: this is the privacy boundary for the client conversation.
        form_submission = db.scalar(select(FormSubmission).where(
            FormSubmission.booking_id == booking.id,
            FormSubmission.form_type == "booking_form",
        ))
        form_answers = dict(booking.form_data or {})
        if form_submission and isinstance(form_submission.data, dict):
            form_answers.update(form_submission.data)
        client_emails: list[str] = []
        for value in (
            booking.client.email,
            form_answers.get("primary_email"),
            form_answers.get("partner_email"),
        ):
            address = str(value or "").strip().lower()
            if (address and address not in client_emails
                    and re.fullmatch(r'[^@\s"]+@[^@\s"]+', address)):
                client_emails.append(address)
        if not client_emails:
            raise HTTPException(409, "This booking does not have a valid client email address")

        sent: list[dict] = []
        logs = db.scalars(select(EmailLog).where(
            EmailLog.booking_id == booking.id,
            EmailLog.status == "sent",
            EmailLog.template_key.notin_(("new_enquiry_admin", "mail_reply")),
            func.lower(EmailLog.recipient).in_(client_emails),
        ).order_by(EmailLog.sent_at).limit(limit)).all()
        for row in logs:
            sent.append({
                "id": f"email-log:{row.id}",
                "direction": "sent",
                "source": "booking_system",
                "subject": row.subject,
                "body": row.body,
                "body_available": bool(row.body),
                "address": row.recipient,
                "date": row.sent_at.isoformat(),
                "status": row.status,
                "attachments": [],
            })

        replies = db.scalars(select(MailboxReply).where(
            MailboxReply.booking_id == booking.id,
            MailboxReply.brand == booking.brand,
            MailboxReply.status == "sent",
            func.lower(MailboxReply.recipient).in_(client_emails),
        ).order_by(MailboxReply.sent_at).limit(limit)).all()
        reply_message_ids = {str(row.message_id) for row in replies if row.message_id}
        for row in replies:
            sent.append({
                "id": f"mailbox-reply:{row.id}",
                "direction": "sent",
                "source": "mailbox_reply",
                "subject": row.subject,
                "body": row.body,
                "body_available": True,
                "address": row.recipient,
                "date": row.sent_at.isoformat(),
                "status": row.status,
                "attachments": [],
            })

        received: list[dict] = []
        incoming_error = None
        mailbox_configured = imap_ready(booking.brand)
        if booking.is_test:
            incoming_error = "Testing Mode records do not read personal or test-mailbox conversations."
        elif mailbox_configured:
            mail_errors: list[str] = []
            received_uids: set[str] = set()
            sent_uids: set[str] = set()
            for client_email in client_emails:
                try:
                    incoming = list_correspondent_messages(
                        booking.brand, client_email, limit
                    )
                    for row in incoming:
                        uid = str(row["uid"])
                        if uid in received_uids:
                            continue
                        received_uids.add(uid)
                        received.append({
                            "id": f"imap:{booking.brand.value}:{uid}",
                            "direction": "received",
                            "source": "hostinger_imap",
                            "subject": row["subject"],
                            "body": row["body"],
                            "body_available": True,
                            "address": row["reply_to_email"],
                            "from_name": row["from_name"],
                            "date": row["date"],
                            "status": "unread" if row["unread"] else "read",
                            "unread": row["unread"],
                            "brand": booking.brand.value,
                            "uid": uid,
                            "attachments": [{
                                **item,
                                "url": (f"/api/mail/{booking.brand.value}/messages/{uid}"
                                        f"/attachments/{item['index']}"),
                            } for item in row["attachments"]],
                        })
                except Exception as exc:
                    mail_errors.append(f"Received mail for {client_email}: {friendly_mail_error(exc)}")

                try:
                    sent_folder_rows = list_sent_messages_to_correspondent(
                        booking.brand, client_email, limit
                    )
                    for row in sent_folder_rows:
                        uid = str(row["uid"])
                        if uid in sent_uids or row.get("message_id") in reply_message_ids:
                            continue
                        sent_uids.add(uid)
                        sent.append({
                            "id": f"imap-sent:{booking.brand.value}:{uid}",
                            "direction": "sent",
                            "source": "hostinger_sent",
                            "subject": row["subject"],
                            "body": row["body"],
                            "body_available": True,
                            "address": row["to_email"],
                            "date": row["date"],
                            "status": "sent",
                            "attachments": [],
                        })
                except Exception as exc:
                    mail_errors.append(f"Sent mail for {client_email}: {friendly_mail_error(exc)}")
            if mail_errors:
                incoming_error = " ".join(mail_errors)[:1000]
        else:
            incoming_error = "The business inbox is not configured."

        messages = sorted(
            [*sent, *received],
            key=lambda item: (item.get("date") or "", item["id"]),
        )
        return {
            "booking_id": booking.id,
            "client_name": booking.title,
            "client_email": booking.client.email,
            "client_emails": client_emails,
            "brand": booking.brand.value,
            "messages": messages,
            "sent_count": len(sent),
            "received_count": len(received),
            "mailbox_configured": mailbox_configured,
            "incoming_error": incoming_error,
            "privacy_scope": "Exact booking and couple email addresses only",
        }

    @app.get("/api/mail/{brand}/messages/{uid}")
    def mail_message(
        brand: str,
        uid: str,
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        selected = _brand(brand)
        try:
            message = read_inbox_message(selected, uid, mark_seen=True)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc))
        except Exception as exc:
            raise HTTPException(503, friendly_mail_error(exc))
        booking = _booking_match(db, message["reply_to_email"], selected)
        message["booking"] = _booking_json(booking)
        message["replies"] = _thread_replies(
            db, selected, message["reply_to_email"], message["message_id"]
        )
        message["account_link_available"] = bool(
            booking and booking.legacy_source != "studio_ninja"
            and booking.status != RecordStatus.CANCELLED
        )
        return message

    @app.patch("/api/mail/{brand}/messages/{uid}/seen")
    def mail_seen(
        brand: str,
        uid: str,
        payload: MailSeenIn,
        _: Admin = Depends(current_admin),
    ):
        selected = _brand(brand)
        try:
            set_seen(selected, uid, payload.seen)
        except Exception as exc:
            raise HTTPException(503, friendly_mail_error(exc))
        return {"ok": True, "seen": payload.seen}

    @app.get("/api/mail/{brand}/messages/{uid}/attachments/{index}")
    def mail_attachment(
        brand: str,
        uid: str,
        index: int,
        _: Admin = Depends(current_admin),
    ):
        selected = _brand(brand)
        try:
            content, filename, content_type = read_attachment(selected, uid, index)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc))
        except Exception as exc:
            raise HTTPException(503, friendly_mail_error(exc))
        if len(content) > get_settings().max_upload_mb * 1024 * 1024:
            raise HTTPException(413, "This attachment is too large to open through the booking system")
        safe_name = filename.replace("\r", "").replace("\n", "").replace('"', "'")[:240]
        return StreamingResponse(
            BytesIO(content), media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{safe_name}"',
                     "X-Content-Type-Options": "nosniff"},
        )

    @app.post("/api/mail/{brand}/messages/{uid}/reply", status_code=201)
    def mail_reply(
        brand: str,
        uid: str,
        payload: MailReplyIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        selected = _brand(brand)
        if not smtp_ready(selected):
            raise HTTPException(503, "SMTP is not configured for this business mailbox")
        try:
            original = read_inbox_message(selected, uid, mark_seen=True)
        except Exception as exc:
            raise HTTPException(503, friendly_mail_error(exc))
        recipient = original["reply_to_email"]
        if not recipient:
            raise HTTPException(422, "This email does not have a reply address")
        booking = None
        if payload.booking_id:
            booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(
                Booking.id == payload.booking_id,
                Booking.brand == selected,
            ))
            if not booking:
                raise HTTPException(404, "The linked booking was not found")
            if booking.client.email.lower() != recipient.lower():
                raise HTTPException(422, "That booking belongs to a different email address")
        else:
            booking = _booking_match(db, recipient, selected)
        body = payload.body.strip()
        portal_url = None
        if payload.include_account_link and booking:
            portal_url = _new_portal_url(db, booking)
            if portal_url:
                label = ("OPEN YOUR WEDDING ACCOUNT" if selected == Brand.WBM
                         else "OPEN YOUR CLIENT ACCOUNT")
                body = f"{body}\n\n[{label}]({portal_url})"
        profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == selected))
        if not profile:
            raise HTTPException(503, "Business profile not found")
        message = build_reply_message(
            selected, profile, recipient, original["subject"], body,
            original["message_id"], original["references"],
        )
        reply_row = MailboxReply(
            brand=selected,
            booking_id=booking.id if booking else None,
            recipient=recipient,
            subject=str(message["Subject"]),
            body=body,
            message_id=str(message["Message-ID"]),
            in_reply_to=original["message_id"] or None,
            thread_references=str(message.get("References") or "") or None,
            status="sending",
        )
        db.add(reply_row)
        db.flush()
        try:
            send_email_message(message, selected)
            reply_row.status = "sent"
            reply_row.copied_to_sent = append_to_sent(selected, message)
            if booking:
                db.add(EmailLog(
                    booking_id=booking.id, template_key="mail_reply",
                    recipient=recipient, subject=str(message["Subject"]), status="sent",
                ))
            audit(db, "reply_to_client_email", "mailbox_reply", reply_row.id, {
                "brand": selected.value,
                "booking_id": booking.id if booking else None,
                "recipient": recipient,
                "copied_to_sent": reply_row.copied_to_sent,
                "account_link_included": bool(portal_url),
                "admin": admin.email,
            })
            db.commit()
        except Exception as exc:
            reply_row.status = "failed"
            reply_row.error = str(exc)[:2000]
            db.commit()
            raise HTTPException(503, friendly_mail_error(exc))
        return {
            "ok": True,
            "recipient": recipient,
            "subject": str(message["Subject"]),
            "booking": _booking_json(booking),
            "account_link_included": bool(portal_url),
            "account_link_skipped_for_import": bool(
                payload.include_account_link and booking
                and booking.legacy_source == "studio_ninja"
            ),
            "copied_to_sent": reply_row.copied_to_sent,
            "sent_at": reply_row.sent_at.isoformat(),
        }

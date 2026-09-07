"""Reliable, opt-in synchronisation with the Weddings By Mark Growth Engine.

The booking database always wins for booking, quote and payment state. A
content hash makes snapshots idempotent and local state ensures an unavailable
Growth Engine never blocks normal booking work.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import SessionLocal, get_db
from .models import (Admin, Booking, Brand, Client, GrowthLeadLink,
                     GrowthSyncState, Quote, RecordKind, RecordStatus)
from .security import current_admin
from .services import audit, create_default_tasks

settings = get_settings()
CONFIRMATION = "SYNC BOOKINGS TO GROWTH ENGINE"


class SyncConfirmation(BaseModel):
    confirmation: str = Field(min_length=3, max_length=100)


class GrowthEnquiryIn(BaseModel):
    event_id: str = Field(min_length=8, max_length=160)
    growth_lead_id: str = Field(min_length=8, max_length=100)
    primary_first_name: str = Field(min_length=1, max_length=100)
    partner_first_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    event_date: date
    venue: str = Field(min_length=1, max_length=240)
    venue_address: str | None = Field(default=None, max_length=1000)
    package_interest: str | None = Field(default=None, max_length=160)
    referral_source: str | None = Field(default=None, max_length=160)
    message: str | None = Field(default=None, max_length=5000)
    is_test: bool = False


def _money(value) -> float:
    return float(Decimal(value or 0).quantize(Decimal("0.01")))


def _source_details(booking: Booking) -> tuple[str | None, str | None]:
    website = dict((booking.form_data or {}).get("website_enquiry") or {})
    return website.get("heard_about_us"), booking.notes


def _booking_query():
    query = (
        select(Booking)
        .options(selectinload(Booking.client), selectinload(Booking.quotes))
        .where(Booking.brand == Brand.WBM, Booking.kind == RecordKind.WEDDING)
        .order_by(Booking.created_at)
    )
    if settings.growth_sync_from_date:
        start = datetime.combine(settings.growth_sync_from_date, datetime.min.time(), tzinfo=timezone.utc)
        query = query.where(Booking.created_at >= start)
    return query


def build_booking_payload(booking: Booking) -> tuple[dict, str]:
    referral_source, message = _source_details(booking)
    accepted_quote = next((row for row in booking.quotes if row.status == "accepted"), None)
    latest_quote = max(booking.quotes, key=lambda row: row.created_at, default=None)
    current_quote = accepted_quote or latest_quote
    quote_items = []
    for raw in (current_quote.line_items if current_quote else []) or []:
        if not isinstance(raw, dict):
            continue
        quote_items.append({
            "type": str(raw.get("type") or "item")[:30],
            "code": str(raw.get("code") or "")[:80],
            "name": str(raw.get("name") or "Item")[:180],
            "description": str(raw.get("description") or "")[:1000],
            "quantity": _money(raw.get("quantity") or 1),
            "unit_price": _money(raw.get("unit_price")),
            "total": _money(raw.get("total")),
            "required": bool(raw.get("required", False)),
        })
    payload = {
        "booking_id": booking.id,
        "primary_first_name": booking.client.first_name,
        "partner_first_name": booking.client.partner_name or "Partner",
        "email": booking.client.email,
        "phone": booking.client.phone,
        "event_date": booking.event_date.isoformat() if booking.event_date else None,
        "venue": booking.venue_or_project or "To be confirmed",
        "venue_address": booking.venue_address,
        "package_interest": booking.package_name,
        "referral_source": referral_source or (booking.workflow_state or {}).get("source"),
        "message": message,
        "booking_status": booking.status.value,
        "quote_accepted": bool(accepted_quote),
        "quote_status": current_quote.status if current_quote else None,
        "quote_items": quote_items,
        "deposit_paid": bool(booking.deposit_paid_date),
        "deposit_amount": _money(booking.deposit_amount),
        "estimated_value": _money(booking.quoted_total),
        "is_test": bool(booking.is_test),
        "received_at": booking.created_at.isoformat(),
        "updated_at": (booking.updated_at or booking.created_at).isoformat(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payload["event_id"] = f"booking-snapshot:{booking.id}:{payload_hash[:32]}"
    return payload, payload_hash


def _request_json(path: str, *, method: str = "GET", body: dict | None = None) -> dict:
    if not settings.growth_integration_enabled:
        raise RuntimeError("Growth Engine integration is disabled")
    url = f"{settings.growth_api_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(url, data=data, method=method, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Integration-Key": settings.growth_integration_key or "",
        "User-Agent": "WBM-Booking-System/8.38",
    })
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Growth Engine returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Growth Engine connection failed: {exc}") from exc


def connection_check() -> dict:
    return _request_json("/api/integrations/booking/health")


def integration_status(db: Session) -> dict:
    eligible = pending = synced = errors = 0
    for booking in db.scalars(_booking_query()).unique().all():
        if not booking.event_date:
            continue
        eligible += 1
        _, payload_hash = build_booking_payload(booking)
        state = db.get(GrowthSyncState, booking.id)
        if state and state.status == "synced" and state.payload_hash == payload_hash:
            synced += 1
        else:
            pending += 1
            if state and state.status == "error":
                errors += 1
    return {
        "enabled": settings.growth_integration_enabled,
        "auto_sync": settings.growth_integration_auto_sync,
        "growth_url": settings.growth_api_url,
        "sync_from_date": settings.growth_sync_from_date.isoformat() if settings.growth_sync_from_date else None,
        "eligible": eligible,
        "synced": synced,
        "pending": pending,
        "errors": errors,
    }


def sync_pending(*, maximum: int = 100) -> dict:
    if not settings.growth_integration_enabled:
        raise RuntimeError("Growth Engine integration is disabled")
    attempted = synced = failed = 0
    with SessionLocal() as db:
        for booking in db.scalars(_booking_query()).unique().all():
            if attempted >= maximum or not booking.event_date:
                continue
            payload, payload_hash = build_booking_payload(booking)
            state = db.get(GrowthSyncState, booking.id)
            if state and state.status == "synced" and state.payload_hash == payload_hash:
                continue
            attempted += 1
            state = state or GrowthSyncState(booking_id=booking.id)
            state.event_id = payload["event_id"]
            state.last_attempt_at = datetime.now(timezone.utc)
            try:
                response = _request_json(
                    "/api/integrations/booking/enquiry", method="POST", body=payload
                )
                if not response.get("ok"):
                    raise RuntimeError("Growth Engine did not acknowledge the booking")
                state.payload_hash = payload_hash
                state.status = "synced"
                state.last_error = None
                state.last_synced_at = datetime.now(timezone.utc)
                synced += 1
            except Exception as exc:
                state.status = "error"
                state.last_error = str(exc)[:2000]
                failed += 1
            db.add(state)
            db.commit()
        remaining = integration_status(db)["pending"]
    return {"attempted": attempted, "synced": synced, "failed": failed, "remaining": remaining}


async def growth_sync_loop() -> None:
    while True:
        await asyncio.sleep(max(1, settings.growth_sync_minutes) * 60)
        if not (settings.growth_integration_enabled and settings.growth_integration_auto_sync):
            continue
        try:
            await asyncio.to_thread(sync_pending)
        except Exception:
            # Booking work remains authoritative and the next scan retries.
            pass


def _require_key(value: str | None) -> None:
    if not settings.growth_integration_enabled:
        raise HTTPException(503, "Growth Engine integration is disabled")
    expected = settings.growth_integration_key or ""
    if not expected or not value or not hmac.compare_digest(expected, value):
        raise HTTPException(401, "Integration key is missing or invalid")


def register_growth_integration_routes(app: FastAPI) -> None:
    @app.get("/api/integrations/growth/health")
    def inbound_health(x_integration_key: str | None = Header(default=None)):
        _require_key(x_integration_key)
        return {"ok": True, "app": settings.app_name, "direction": "growth-to-booking"}

    @app.post("/api/integrations/growth/enquiry", status_code=201)
    def receive_growth_enquiry(payload: GrowthEnquiryIn,
                               x_integration_key: str | None = Header(default=None),
                               db: Session = Depends(get_db)):
        _require_key(x_integration_key)
        link = db.get(GrowthLeadLink, payload.growth_lead_id)
        if link:
            return {"ok": True, "already_processed": True, "booking_id": link.booking_id}
        client = Client(
            first_name=payload.primary_first_name.strip(), last_name="",
            partner_name=payload.partner_first_name.strip(), email=str(payload.email).lower(),
            phone=payload.phone.strip() if payload.phone else None,
        )
        db.add(client)
        db.flush()
        booking = Booking(
            brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.ENQUIRY,
            title=f"{payload.primary_first_name.strip()} & {payload.partner_first_name.strip()}",
            client_id=client.id, event_date=payload.event_date,
            venue_or_project=payload.venue.strip(), venue_address=payload.venue_address,
            package_name=payload.package_interest, notes=payload.message,
            form_data={"growth_engine": payload.model_dump(mode="json")},
            workflow_state={"source": "growth_engine", "growth_lead_id": payload.growth_lead_id},
            is_test=payload.is_test,
        )
        db.add(booking)
        db.flush()
        create_default_tasks(db, booking.id, booking.kind, booking.event_date)
        db.add(GrowthLeadLink(growth_lead_id=payload.growth_lead_id, booking_id=booking.id))
        audit(db, "growth_engine_enquiry", "booking", booking.id, {
            "growth_lead_id": payload.growth_lead_id, "event_id": payload.event_id,
            "emails_sent": 0,
        })
        db.commit()
        return {"ok": True, "booking_id": booking.id, "emails_sent": 0}

    @app.get("/api/growth-integration/status")
    def status(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
        return integration_status(db)

    @app.get("/api/growth-integration/connection")
    def connection(_: Admin = Depends(current_admin)):
        try:
            return {"ok": True, "growth_engine": connection_check()}
        except Exception as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/api/growth-integration/sync")
    def sync_now(payload: SyncConfirmation, admin: Admin = Depends(current_admin),
                 db: Session = Depends(get_db)):
        if payload.confirmation.strip() != CONFIRMATION:
            raise HTTPException(422, f"Type {CONFIRMATION} exactly")
        result = sync_pending()
        audit(db, "sync_bookings_to_growth_engine", "integration", None, {
            **result, "admin": admin.email, "emails_sent": 0,
        })
        db.commit()
        return result

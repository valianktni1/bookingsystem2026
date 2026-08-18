"""Safe, one-way mirroring from bookings into the accounts application.

The booking system remains the source of truth.  A content hash makes every
revision idempotent, while the local sync-state table means a failed accounts
request never blocks or rolls back normal booking work.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import SessionLocal, get_db
from .models import AccountsSyncState, Admin, Booking, Brand, Invoice, Payment, RecordKind, RecordStatus
from .security import current_admin
from .services import audit

settings = get_settings()
ACCOUNTING_CUTOFF = date(2025, 4, 6)
CONFIRMATION = "SYNC ELIGIBLE WEDDING INVOICES"


class SyncConfirmation(BaseModel):
    confirmation: str = Field(min_length=3, max_length=100)


def _iso(value):
    return value.isoformat() if value else None


def _money(value) -> float:
    return float(Decimal(value or 0).quantize(Decimal("0.01")))


def _eligible(invoice: Invoice) -> tuple[bool, str]:
    booking = invoice.booking
    if not booking:
        return False, "missing_booking"
    if booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING:
        return False, "not_wbm_wedding"
    if booking.is_test:
        return False, "test_record"
    if booking.status in (RecordStatus.ENQUIRY, RecordStatus.QUOTED):
        return False, "not_an_accepted_job"
    wedding_in_scope = bool(booking.event_date and booking.event_date >= ACCOUNTING_CUTOFF)
    payment_in_scope = any(payment.paid_date >= ACCOUNTING_CUTOFF for payment in invoice.payments)
    if not wedding_in_scope and not payment_in_scope:
        return False, "before_2025_26_scope"
    return True, "wedding_date" if wedding_in_scope else "payment_date_exception"


def _description(invoice: Invoice) -> str:
    lines = []
    for item in invoice.line_items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("description") or "").strip()
        if not name:
            continue
        amount = item.get("amount", item.get("price"))
        lines.append(f"{name}: £{_money(amount):,.2f}" if amount is not None else name)
    if lines:
        return "\n".join(lines)
    return (invoice.description or invoice.booking.package_name or "Wedding booking").strip()


def _cancellation(booking: Booking) -> dict:
    return dict((booking.workflow_state or {}).get("cancellation") or {})


def build_invoice_payload(invoice: Invoice) -> tuple[dict, str]:
    eligible, scope_reason = _eligible(invoice)
    if not eligible:
        raise ValueError(scope_reason)
    booking = invoice.booking
    client = booking.client
    payments = sorted(invoice.payments, key=lambda row: (row.paid_date, row.created_at, row.id))
    cancellation = _cancellation(booking)
    payload = {
        "source_invoice_id": invoice.id,
        "source_booking_id": booking.id,
        "invoice_number": invoice.number,
        "legacy_invoice_number": invoice.legacy_number,
        "issue_date": _iso(invoice.issue_date),
        "brand": booking.brand.value,
        "record_kind": booking.kind.value,
        "is_test": bool(booking.is_test),
        "is_legacy_import": bool(booking.legacy_source),
        "scope_reason": scope_reason,
        "couple_names": booking.title,
        "client_address": client.address if client else None,
        "client_email": client.email if client else None,
        "client_phone": client.phone if client else None,
        "wedding_date": _iso(booking.event_date),
        "venue": booking.venue_or_project,
        "package_name": booking.package_name,
        "description": _description(invoice),
        "line_items": invoice.line_items or [],
        "total_price": _money(invoice.total),
        "due_date": _iso(invoice.due_date or booking.balance_due_date),
        "status": invoice.status,
        "cancellation_date": cancellation.get("cancellation_date"),
        "cancellation_reason": cancellation.get("reason"),
        "void_reason": invoice.notes if invoice.status == "void" else None,
        "payments": [
            {
                "id": payment.id,
                "amount": _money(payment.amount),
                "paid_date": _iso(payment.paid_date),
                "payment_type": payment.payment_type,
                "reference": payment.reference,
                "notes": payment.notes,
            }
            for payment in payments
        ],
        "updated_at": _iso(booking.updated_at or invoice.created_at),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payload["event_id"] = f"invoice-sync:{invoice.id}:{payload_hash[:32]}"
    return payload, payload_hash


def _invoice_query():
    return (
        select(Invoice)
        .join(Booking)
        .options(
            selectinload(Invoice.booking).selectinload(Booking.client),
            selectinload(Invoice.payments),
        )
        .where(Booking.brand == Brand.WBM, Booking.kind == RecordKind.WEDDING)
        .order_by(Invoice.sequence)
    )


def _request_json(path: str, *, method: str = "GET", body: dict | None = None) -> dict:
    if not settings.accounts_integration_enabled:
        raise RuntimeError("Accounts integration is disabled")
    url = f"{settings.accounts_api_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(url, data=data, method=method, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Accounts-Integration-Key": settings.accounts_integration_key or "",
    })
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Accounts returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Accounts connection failed: {exc}") from exc


def connection_check() -> dict:
    return _request_json("/api/integrations/booking/health")


def integration_status(db: Session) -> dict:
    eligible = pending = synced = errors = 0
    for invoice in db.scalars(_invoice_query()).unique().all():
        allowed, _ = _eligible(invoice)
        if not allowed:
            continue
        eligible += 1
        payload, payload_hash = build_invoice_payload(invoice)
        state = db.get(AccountsSyncState, invoice.id)
        if state and state.status == "synced" and state.payload_hash == payload_hash:
            synced += 1
        else:
            pending += 1
            if state and state.status == "error":
                errors += 1
    latest = db.scalar(select(AccountsSyncState).where(
        AccountsSyncState.last_synced_at.is_not(None)
    ).order_by(AccountsSyncState.last_synced_at.desc()))
    return {
        "enabled": settings.accounts_integration_enabled,
        "auto_sync": settings.accounts_integration_auto_sync,
        "accounts_url": settings.accounts_api_url,
        "cutoff": ACCOUNTING_CUTOFF.isoformat(),
        "eligible": eligible,
        "synced": synced,
        "pending": pending,
        "errors": errors,
        "last_synced_at": _iso(latest.last_synced_at) if latest else None,
    }


def sync_pending(*, maximum: int = 500) -> dict:
    if not settings.accounts_integration_enabled:
        raise RuntimeError("Accounts integration is disabled")
    with SessionLocal() as db:
        candidates = []
        for invoice in db.scalars(_invoice_query()).unique().all():
            allowed, _ = _eligible(invoice)
            if not allowed:
                continue
            payload, payload_hash = build_invoice_payload(invoice)
            state = db.get(AccountsSyncState, invoice.id)
            if state and state.status == "synced" and state.payload_hash == payload_hash:
                continue
            candidates.append((invoice.id, payload, payload_hash))
            if len(candidates) >= maximum:
                break
        if not candidates:
            return {"attempted": 0, "synced": 0, "failed": 0, "remaining": 0}

        now = datetime.now(timezone.utc)
        try:
            response = _request_json(
                "/api/integrations/booking/invoices/batch",
                method="POST",
                body={"invoices": [row[1] for row in candidates]},
            )
            accepted = {
                str(item.get("source_invoice_id"))
                for item in response.get("results", [])
                if item.get("status") in ("synchronised", "already_processed")
            }
            for invoice_id, payload, payload_hash in candidates:
                state = db.get(AccountsSyncState, invoice_id) or AccountsSyncState(invoice_id=invoice_id)
                state.last_attempt_at = now
                state.event_id = payload["event_id"]
                if invoice_id in accepted:
                    state.payload_hash = payload_hash
                    state.status = "synced"
                    state.last_error = None
                    state.last_synced_at = now
                else:
                    state.status = "error"
                    state.last_error = "Accounts did not confirm this invoice"
                db.add(state)
            db.commit()
        except Exception as exc:
            for invoice_id, payload, _ in candidates:
                state = db.get(AccountsSyncState, invoice_id) or AccountsSyncState(invoice_id=invoice_id)
                state.status = "error"
                state.event_id = payload["event_id"]
                state.last_attempt_at = now
                state.last_error = str(exc)[:2000]
                db.add(state)
            db.commit()
            raise

        status = integration_status(db)
        return {
            "attempted": len(candidates),
            "synced": len(accepted),
            "failed": len(candidates) - len(accepted),
            "remaining": status["pending"],
        }


async def accounts_sync_loop() -> None:
    import asyncio

    while True:
        await asyncio.sleep(max(2, settings.accounts_sync_minutes) * 60)
        if not (settings.accounts_integration_enabled and settings.accounts_integration_auto_sync):
            continue
        try:
            await asyncio.to_thread(sync_pending)
        except Exception:
            # The saved error state is shown in Business settings. Booking work
            # continues normally and the next scan retries the current revision.
            pass


def register_accounts_integration_routes(app: FastAPI) -> None:
    @app.get("/api/accounts-integration/status")
    def status(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
        return integration_status(db)

    @app.get("/api/accounts-integration/connection")
    def connection(_: Admin = Depends(current_admin)):
        try:
            return {"ok": True, "accounts": connection_check()}
        except Exception as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/api/accounts-integration/sync")
    def sync_now(payload: SyncConfirmation, admin: Admin = Depends(current_admin),
                 db: Session = Depends(get_db)):
        if payload.confirmation.strip() != CONFIRMATION:
            raise HTTPException(422, f"Type {CONFIRMATION} exactly")
        try:
            result = sync_pending()
        except Exception as exc:
            raise HTTPException(502, str(exc)) from exc
        audit(db, "sync_wedding_invoices_to_accounts", "integration", None, {
            **result, "admin": admin.email, "emails_sent": 0,
        })
        db.commit()
        return result

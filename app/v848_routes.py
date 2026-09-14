"""V8.48 audited date security for exceptional pay-later agreements."""

from __future__ import annotations

import copy
import re
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .google_calendar import sync_booking_calendar_safely
from .models import Admin, Booking, Brand, Invoice, RecordKind, RecordStatus
from .payment_arrangements import (
    WORKFLOW_KEY,
    active_payment_arrangement,
    arrangement_json,
    genuine_payment_exists,
    payment_arrangement,
)
from .security import current_admin
from .services import audit


class SecureWithoutPaymentIn(BaseModel):
    agreed_payment_date: date
    reason: str = Field(min_length=10, max_length=2000)
    pause_payment_reminders: bool = True
    confirmation: str = Field(max_length=100)


class RemoveArrangementIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)
    confirmation: str = Field(max_length=100)


def _serialise_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _arrangement_note(invoice: Invoice, agreed_date: date) -> str:
    existing = str(invoice.notes or "").strip()
    existing = re.sub(
        r"Booking fee of £[\d,.]+ is due by [^.]+\.\s*",
        "",
        existing,
        flags=re.IGNORECASE,
    )
    existing = re.sub(
        r"The remaining balance is due by [^.]+\.\s*",
        "",
        existing,
        flags=re.IGNORECASE,
    ).strip()
    wording = (
        f"Special written payment arrangement: no payment has yet been received. "
        f"The outstanding balance is due on {agreed_date.strftime('%d %B %Y')}."
    )
    return f"{wording}\n\n{existing}" if existing else wording


def _arranged_schedule(invoice: Invoice, agreed_date: date) -> list[dict]:
    rows = []
    for raw in invoice.payment_schedule or []:
        row = dict(raw)
        row["due_date"] = agreed_date.isoformat()
        rows.append(row)
    return rows


def _load_booking(db: Session, booking_id: str) -> Booking:
    booking = db.scalar(select(Booking).options(
        selectinload(Booking.client),
        selectinload(Booking.quotes),
        selectinload(Booking.invoices).selectinload(Invoice.payments),
    ).where(Booking.id == booking_id))
    if not booking:
        raise HTTPException(404, "Wedding booking not found")
    return booking


def _lock_booking_invoices(db: Session, booking: Booking) -> None:
    """Serialise the exception with genuine payment entry on any invoice."""
    db.scalars(select(Invoice).where(
        Invoice.booking_id == booking.id
    ).order_by(Invoice.id).with_for_update()).all()
    db.refresh(booking)


def _accepted_invoice(booking: Booking) -> Invoice | None:
    quote = next((row for row in booking.quotes if row.status == "accepted"), None)
    if not quote or not quote.invoice_id:
        return None
    return next((row for row in booking.invoices if row.id == quote.invoice_id), None)


def _restore_if_unchanged(target, field: str, previous, applied) -> None:
    current = getattr(target, field)
    if current == applied:
        setattr(target, field, previous)


def register_v848_routes(app: FastAPI) -> None:
    @app.post("/api/bookings/{booking_id}/payment-arrangement")
    def secure_without_payment(
        booking_id: str,
        payload: SecureWithoutPaymentIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = _load_booking(db, booking_id)
        _lock_booking_invoices(db, booking)
        if payload.confirmation != "SECURE WITHOUT PAYMENT":
            raise HTTPException(422, "Type SECURE WITHOUT PAYMENT exactly to confirm")
        if booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING:
            raise HTTPException(409, "This exception is available only for Weddings By Mark weddings")
        if booking.legacy_source or booking.is_test:
            raise HTTPException(409, "This exception is only for genuine native wedding bookings")
        if booking.status in (RecordStatus.CANCELLED, RecordStatus.COMPLETED):
            raise HTTPException(409, "A cancelled or completed wedding cannot use this arrangement")
        if not booking.event_date:
            raise HTTPException(422, "Set the wedding date before securing it")
        if payload.agreed_payment_date < date.today():
            raise HTTPException(422, "The agreed payment date cannot be in the past")
        if payload.agreed_payment_date > booking.event_date:
            raise HTTPException(422, "The agreed payment date cannot be after the wedding")
        if genuine_payment_exists(db, booking.id):
            raise HTTPException(409, "A genuine payment already secures this wedding")
        if active_payment_arrangement(booking):
            raise HTTPException(409, "This wedding already has an active payment arrangement")
        invoice = _accepted_invoice(booking)
        if not invoice or invoice.status in ("paid", "void", "cancelled"):
            raise HTTPException(409, "An active accepted quote invoice is required first")

        now = datetime.now(timezone.utc).isoformat()
        previous = {
            "booking_status": booking.status.value,
            "booking_balance_due_date": _serialise_date(booking.balance_due_date),
            "invoice": {
                "id": invoice.id,
                "deposit_due_date": _serialise_date(invoice.deposit_due_date),
                "due_date": _serialise_date(invoice.due_date),
                "payment_schedule": copy.deepcopy(invoice.payment_schedule or []),
                "notes": invoice.notes,
            },
        }
        arranged_schedule = _arranged_schedule(invoice, payload.agreed_payment_date)
        arranged_notes = _arrangement_note(invoice, payload.agreed_payment_date)
        applied = {
            "booking_status": RecordStatus.CONFIRMED.value,
            "booking_balance_due_date": payload.agreed_payment_date.isoformat(),
            "invoice": {
                "id": invoice.id,
                "deposit_due_date": payload.agreed_payment_date.isoformat(),
                "due_date": payload.agreed_payment_date.isoformat(),
                "payment_schedule": copy.deepcopy(arranged_schedule),
                "notes": arranged_notes,
            },
        }
        earlier = payment_arrangement(booking)
        history = list(earlier.get("history") or [])
        history.append({
            "action": "secured_without_payment",
            "at": now,
            "by": admin.email,
            "agreed_payment_date": payload.agreed_payment_date.isoformat(),
            "reason": payload.reason.strip(),
        })
        arrangement = {
            "status": "active",
            "active": True,
            "agreed_payment_date": payload.agreed_payment_date.isoformat(),
            "reason": payload.reason.strip(),
            "pause_payment_reminders": payload.pause_payment_reminders,
            "secured_at": now,
            "secured_by": admin.email,
            "previous": previous,
            "applied": applied,
            "history": history[-50:],
        }
        workflow = dict(booking.workflow_state or {})
        workflow[WORKFLOW_KEY] = arrangement
        booking.workflow_state = workflow
        booking.status = RecordStatus.CONFIRMED
        booking.balance_due_date = payload.agreed_payment_date
        invoice.deposit_due_date = payload.agreed_payment_date
        invoice.due_date = payload.agreed_payment_date
        invoice.payment_schedule = arranged_schedule
        invoice.notes = arranged_notes
        audit(db, "secure_without_payment", "booking", booking.id, {
            "agreed_payment_date": payload.agreed_payment_date.isoformat(),
            "reason": payload.reason.strip(),
            "pause_payment_reminders": payload.pause_payment_reminders,
            "invoice_id": invoice.id,
            "invoice_number": invoice.number,
            "payment_record_created": False,
        })
        db.commit()
        calendar = sync_booking_calendar_safely(db, booking)
        return {
            "ok": True,
            "message": "Date secured by special payment arrangement; no payment was recorded",
            "payment_arrangement": arrangement_json(booking),
            "google_calendar": calendar,
        }

    @app.delete("/api/bookings/{booking_id}/payment-arrangement")
    def remove_payment_arrangement(
        booking_id: str,
        payload: RemoveArrangementIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = _load_booking(db, booking_id)
        _lock_booking_invoices(db, booking)
        if payload.confirmation != "REMOVE PAYMENT ARRANGEMENT":
            raise HTTPException(422, "Type REMOVE PAYMENT ARRANGEMENT exactly to confirm")
        arrangement = payment_arrangement(booking)
        if arrangement.get("status") != "active":
            raise HTTPException(409, "There is no active exceptional payment arrangement")
        if genuine_payment_exists(db, booking.id):
            raise HTTPException(409, "A genuine payment exists; remove or correct that payment first")
        if booking.status != RecordStatus.CONFIRMED:
            raise HTTPException(409, "Return this wedding to the secured stage before removing the arrangement")

        previous = dict(arrangement.get("previous") or {})
        applied = dict(arrangement.get("applied") or {})
        invoice_previous = dict(previous.get("invoice") or {})
        invoice_applied = dict(applied.get("invoice") or {})
        invoice = next((row for row in booking.invoices if row.id == invoice_previous.get("id")), None)
        if invoice:
            _restore_if_unchanged(
                invoice, "deposit_due_date",
                date.fromisoformat(invoice_previous["deposit_due_date"]) if invoice_previous.get("deposit_due_date") else None,
                date.fromisoformat(invoice_applied["deposit_due_date"]) if invoice_applied.get("deposit_due_date") else None,
            )
            _restore_if_unchanged(
                invoice, "due_date",
                date.fromisoformat(invoice_previous["due_date"]) if invoice_previous.get("due_date") else None,
                date.fromisoformat(invoice_applied["due_date"]) if invoice_applied.get("due_date") else None,
            )
            _restore_if_unchanged(
                invoice, "payment_schedule",
                copy.deepcopy(invoice_previous.get("payment_schedule") or []),
                copy.deepcopy(invoice_applied.get("payment_schedule") or []),
            )
            _restore_if_unchanged(
                invoice, "notes", invoice_previous.get("notes"), invoice_applied.get("notes")
            )
        previous_balance = previous.get("booking_balance_due_date")
        applied_balance = applied.get("booking_balance_due_date")
        _restore_if_unchanged(
            booking, "balance_due_date",
            date.fromisoformat(previous_balance) if previous_balance else None,
            date.fromisoformat(applied_balance) if applied_balance else None,
        )
        previous_status = previous.get("booking_status") or RecordStatus.QUOTED.value
        booking.status = RecordStatus(previous_status)
        now = datetime.now(timezone.utc).isoformat()
        arrangement.update({
            "status": "removed",
            "active": False,
            "ended_at": now,
            "ended_by": admin.email,
            "end_reason": payload.reason.strip(),
        })
        history = list(arrangement.get("history") or [])
        history.append({
            "action": "removed",
            "at": now,
            "by": admin.email,
            "reason": payload.reason.strip(),
        })
        arrangement["history"] = history[-50:]
        workflow = dict(booking.workflow_state or {})
        workflow[WORKFLOW_KEY] = arrangement
        booking.workflow_state = workflow
        audit(db, "remove_payment_arrangement", "booking", booking.id, {
            "reason": payload.reason.strip(),
            "restored_status": booking.status.value,
            "payment_record_deleted": False,
        })
        db.commit()
        calendar = sync_booking_calendar_safely(db, booking)
        return {
            "ok": True,
            "message": "Special payment arrangement removed; the date is provisional again",
            "payment_arrangement": arrangement_json(booking),
            "google_calendar": calendar,
        }

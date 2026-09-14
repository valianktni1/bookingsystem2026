"""Truthful exceptional-payment arrangements for native wedding bookings.

An active arrangement secures the wedding date without creating a Payment.
The complete explanation and the previous invoice dates are retained inside the
existing booking workflow JSON, so no database migration is required.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Booking, Invoice, Payment


WORKFLOW_KEY = "payment_arrangement"


def payment_arrangement(booking: Booking) -> dict:
    raw = (booking.workflow_state or {}).get(WORKFLOW_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def active_payment_arrangement(booking: Booking) -> bool:
    return payment_arrangement(booking).get("status") == "active"


def arrangement_json(booking: Booking) -> dict | None:
    arrangement = payment_arrangement(booking)
    if not arrangement:
        return None
    return {
        "active": arrangement.get("status") == "active",
        "status": arrangement.get("status"),
        "agreed_payment_date": arrangement.get("agreed_payment_date"),
        "reason": arrangement.get("reason"),
        "pause_payment_reminders": bool(arrangement.get("pause_payment_reminders", True)),
        "secured_at": arrangement.get("secured_at"),
        "secured_by": arrangement.get("secured_by"),
        "ended_at": arrangement.get("ended_at"),
        "ended_by": arrangement.get("ended_by"),
        "end_reason": arrangement.get("end_reason"),
    }


def genuine_payment_exists(db: Session, booking_id: str) -> bool:
    return db.scalar(select(Payment.id).join(
        Invoice, Invoice.id == Payment.invoice_id
    ).where(Invoice.booking_id == booking_id).limit(1)) is not None


def complete_arrangement_after_payment(
    booking: Booking,
    paid_date: date,
    changed_by: str,
) -> bool:
    """End an active exception after real money is recorded, retaining history."""
    arrangement = payment_arrangement(booking)
    if arrangement.get("status") != "active":
        return False
    now = datetime.now(timezone.utc).isoformat()
    arrangement.update({
        "status": "completed_by_payment",
        "active": False,
        "ended_at": now,
        "ended_by": changed_by,
        "end_reason": "A genuine payment was recorded",
        "first_payment_date": paid_date.isoformat(),
    })
    history = list(arrangement.get("history") or [])
    history.append({
        "action": "completed_by_payment",
        "at": now,
        "by": changed_by,
        "paid_date": paid_date.isoformat(),
    })
    arrangement["history"] = history[-50:]
    workflow = dict(booking.workflow_state or {})
    workflow[WORKFLOW_KEY] = arrangement
    booking.workflow_state = workflow
    return True


def reactivate_arrangement_after_payment_deletion(
    booking: Booking,
    changed_by: str,
) -> bool:
    """Restore the agreed protection if the only payment was removed as a mistake."""
    arrangement = payment_arrangement(booking)
    if arrangement.get("status") != "completed_by_payment":
        return False
    now = datetime.now(timezone.utc).isoformat()
    arrangement.update({
        "status": "active",
        "active": True,
        "ended_at": None,
        "ended_by": None,
        "end_reason": None,
        "first_payment_date": None,
    })
    history = list(arrangement.get("history") or [])
    history.append({
        "action": "reactivated_after_payment_deletion",
        "at": now,
        "by": changed_by,
    })
    arrangement["history"] = history[-50:]
    workflow = dict(booking.workflow_state or {})
    workflow[WORKFLOW_KEY] = arrangement
    booking.workflow_state = workflow
    return True

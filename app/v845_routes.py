"""V8.45 everyday workflow actions.

These routes deliberately store workflow history in ``Booking.workflow_state``
so the release needs no destructive schema migration.  None of the actions in
this module sends a client email.  Existing invoices, payments, submitted forms
and signed agreement snapshots are retained unchanged unless a wedding date
requires the live invoice schedule to move with it.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .google_calendar import sync_booking_calendar_safely
from .mail_service import imap_ready, list_inbox_messages
from .models import (
    Admin,
    Booking,
    Brand,
    ClientPortalToken,
    ContractAcceptance,
    DateBlock,
    EmailLog,
    Invoice,
    Payment,
    Quote,
    RecordKind,
    RecordStatus,
    ReminderLog,
    Task,
)
from .security import current_admin
from .services import audit
from .v84_routes import quote_followup_paused


class CloseEnquiryIn(BaseModel):
    outcome: Literal[
        "booked_elsewhere",
        "no_response",
        "date_unavailable",
        "budget",
        "plans_changed",
        "other",
    ]
    details: str | None = Field(default=None, max_length=1000)


class RescheduleWeddingIn(BaseModel):
    new_date: date
    reason: str = Field(min_length=3, max_length=1000)
    confirm_conflicts: bool = False


ENQUIRY_OUTCOMES = {
    "booked_elsewhere": "Booked another photographer",
    "no_response": "No response",
    "date_unavailable": "Date unavailable",
    "budget": "Budget / price",
    "plans_changed": "Plans changed",
    "other": "Other reason",
}


def _has_accepted_quote(db: Session, booking_id: str) -> bool:
    return db.scalar(select(Quote.id).where(
        Quote.booking_id == booking_id,
        Quote.status == "accepted",
    ).limit(1)) is not None


def _has_payment(db: Session, booking_id: str) -> bool:
    return db.scalar(select(Payment.id).join(
        Invoice, Invoice.id == Payment.invoice_id
    ).where(Invoice.booking_id == booking_id).limit(1)) is not None


def _date_conflicts(db: Session, booking: Booking, new_date: date) -> dict:
    blocks = list(db.scalars(select(DateBlock).where(
        DateBlock.deleted_at.is_(None),
        DateBlock.start_date <= new_date,
        DateBlock.end_date >= new_date,
    )).all())
    records = list(db.scalars(select(Booking).where(
        Booking.id != booking.id,
        Booking.brand == Brand.WBM,
        Booking.kind == RecordKind.WEDDING,
        Booking.is_test.is_(False),
        Booking.event_date == new_date,
        Booking.status != RecordStatus.CANCELLED,
        Booking.status.in_((
            RecordStatus.ENQUIRY,
            RecordStatus.QUOTED,
            RecordStatus.CONFIRMED,
            RecordStatus.IN_PROGRESS,
        )),
        or_(
            Booking.archived_at.is_(None),
            Booking.status.in_((RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS)),
        ),
    )).all())
    return {
        "blocked_dates": [{
            "id": row.id,
            "label": row.label,
            "start_date": row.start_date.isoformat(),
            "end_date": row.end_date.isoformat(),
        } for row in blocks],
        "records": [{
            "id": row.id,
            "title": row.title,
            "status": row.status.value,
        } for row in records],
        "count": len(blocks) + len(records),
    }


def _iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def apply_quote_reply_safety(
    db: Session,
    bookings: list[Booking],
    *,
    today: date,
    now: datetime,
) -> int:
    """Pause only the next-day quote check when a real reply is detected.

    The final nine-day check deliberately remains independent, matching Mark's
    choice to keep it available after an early conversation.  Mailbox failure
    never blocks the established reminder runner.
    """
    candidates: list[tuple[Booking, datetime]] = []
    for booking in bookings:
        if (
            booking.brand != Brand.WBM
            or booking.kind != RecordKind.WEDDING
            or booking.status not in (RecordStatus.ENQUIRY, RecordStatus.QUOTED)
            or booking.legacy_source
            or booking.automation_suppressed
            or quote_followup_paused(booking, "quote_followup_1")
            or any(quote.status == "accepted" for quote in booking.quotes)
        ):
            continue
        quote_sent_at = db.scalar(select(EmailLog.sent_at).where(
            EmailLog.booking_id == booking.id,
            EmailLog.template_key == "quote",
            EmailLog.status == "sent",
        ).order_by(EmailLog.sent_at.desc()).limit(1))
        if not quote_sent_at:
            continue
        if quote_sent_at.tzinfo is None:
            quote_sent_at = quote_sent_at.replace(tzinfo=timezone.utc)
        days_since = (today - quote_sent_at.date()).days
        if not 1 <= days_since < 9:
            continue
        already_sent = db.scalar(select(EmailLog.id).where(
            EmailLog.booking_id == booking.id,
            EmailLog.template_key == "quote_followup_1",
            EmailLog.status == "sent",
        ).limit(1))
        if not already_sent:
            candidates.append((booking, quote_sent_at.astimezone(timezone.utc)))

    if not candidates or not imap_ready(Brand.WBM):
        return 0
    try:
        inbox = list_inbox_messages(Brand.WBM, limit=200)
    except Exception:
        return 0

    paused = 0
    for booking, quote_sent_at in candidates:
        client_email = str(booking.client.email or "").strip().lower()
        replies = []
        for message in inbox:
            sender = str(message.get("reply_to_email") or message.get("from_email") or "").strip().lower()
            received_at = _iso_datetime(message.get("date"))
            if sender == client_email and received_at and received_at > quote_sent_at:
                replies.append((received_at, str(message.get("uid") or "")))
        if not replies:
            continue
        first_reply_at, uid = min(replies, key=lambda item: item[0])
        workflow = dict(booking.workflow_state or {})
        controls = dict(workflow.get("quote_followup_controls") or {})
        controls["quote_followup_1"] = {
            "paused": True,
            "changed_at": now.isoformat(),
            "changed_by": "system:reply-detection",
            "reason": "Couple replied after the quote was sent",
        }
        workflow["quote_followup_controls"] = controls
        workflow["quote_reply_detection"] = {
            "detected_at": now.isoformat(),
            "first_reply_at": first_reply_at.isoformat(),
            "mail_uid": uid,
            "next_day_followup_paused": True,
            "final_followup_unchanged": True,
        }
        booking.workflow_state = workflow
        audit(db, "auto_pause_quote_followup_after_reply", "booking", booking.id, {
            "first_reply_at": first_reply_at.isoformat(),
            "paused_followup": "quote_followup_1",
            "final_followup_unchanged": True,
            "client_email_sent": False,
        })
        paused += 1
    if paused:
        db.commit()
    return paused


def register_v845_routes(
    app: FastAPI,
    *,
    refresh_payment_dates: Callable[[Session, Booking], None],
    sync_final_call_task: Callable[[Session, Booking], Task | None],
) -> None:
    @app.post("/api/bookings/{booking_id}/close-enquiry")
    def close_enquiry(
        booking_id: str,
        payload: CloseEnquiryIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = db.scalar(select(Booking).options(
            selectinload(Booking.tasks),
            selectinload(Booking.invoices).selectinload(Invoice.payments),
        ).where(Booking.id == booking_id))
        if not booking:
            raise HTTPException(404, "Enquiry not found")
        if booking.kind != RecordKind.WEDDING or booking.brand != Brand.WBM:
            raise HTTPException(409, "This action is only for Weddings By Mark enquiries")
        if booking.status not in (RecordStatus.ENQUIRY, RecordStatus.QUOTED):
            raise HTTPException(409, "Only an open enquiry or unaccepted quote can be closed here")
        if _has_accepted_quote(db, booking.id) or _has_payment(db, booking.id):
            raise HTTPException(409, "This enquiry has progressed financially; use the protected cancellation flow")
        if payload.outcome == "other" and len(str(payload.details or "").strip()) < 3:
            raise HTTPException(422, "Add a short private reason when choosing Other")
        workflow = dict(booking.workflow_state or {})
        if workflow.get("enquiry_closure"):
            raise HTTPException(409, "This enquiry is already closed")
        closed_at = datetime.now(timezone.utc)
        open_task_ids = [task.id for task in booking.tasks if not task.completed]
        for task in booking.tasks:
            task.completed = True
        workflow["enquiry_closure"] = {
            "outcome": payload.outcome,
            "outcome_label": ENQUIRY_OUTCOMES[payload.outcome],
            "details": str(payload.details or "").strip() or None,
            "closed_at": closed_at.isoformat(),
            "closed_by": admin.email,
            "previous_status": booking.status.value,
            "previous_automation_suppressed": booking.automation_suppressed,
            "open_task_ids": open_task_ids,
            "client_email_sent": False,
        }
        booking.workflow_state = workflow
        booking.automation_suppressed = True
        booking.archived_at = closed_at
        for token in db.scalars(select(ClientPortalToken).where(
            ClientPortalToken.booking_id == booking.id,
            ClientPortalToken.revoked_at.is_(None),
        )).all():
            token.revoked_at = closed_at
        audit(db, "close_unsuccessful_enquiry", "booking", booking.id, {
            "outcome": payload.outcome,
            "outcome_label": ENQUIRY_OUTCOMES[payload.outcome],
            "details": str(payload.details or "").strip() or None,
            "client_email_sent": False,
            "financial_records_changed": False,
        })
        db.commit()
        return {
            "ok": True,
            "archived": True,
            "outcome": payload.outcome,
            "outcome_label": ENQUIRY_OUTCOMES[payload.outcome],
            "message": "Enquiry closed and archived · no client email sent",
        }

    @app.post("/api/bookings/{booking_id}/reopen-enquiry")
    def reopen_enquiry(
        booking_id: str,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = db.scalar(select(Booking).options(selectinload(Booking.tasks)).where(
            Booking.id == booking_id
        ))
        if not booking:
            raise HTTPException(404, "Enquiry not found")
        workflow = dict(booking.workflow_state or {})
        closure = dict(workflow.get("enquiry_closure") or {})
        if not closure:
            raise HTTPException(409, "This enquiry was not closed with the enquiry outcome flow")
        previous_status = str(closure.get("previous_status") or RecordStatus.ENQUIRY.value)
        if previous_status not in (RecordStatus.ENQUIRY.value, RecordStatus.QUOTED.value):
            previous_status = RecordStatus.ENQUIRY.value
        reopen_ids = set(closure.get("open_task_ids") or [])
        for task in booking.tasks:
            if task.id in reopen_ids:
                task.completed = False
        history = list(workflow.get("enquiry_closure_history") or [])
        closure.update({
            "reopened_at": datetime.now(timezone.utc).isoformat(),
            "reopened_by": admin.email,
        })
        history.append(closure)
        workflow["enquiry_closure_history"] = history[-20:]
        workflow.pop("enquiry_closure", None)
        booking.workflow_state = workflow
        booking.status = RecordStatus(previous_status)
        booking.automation_suppressed = bool(closure.get("previous_automation_suppressed", False))
        booking.archived_at = None
        audit(db, "reopen_unsuccessful_enquiry", "booking", booking.id, {
            "restored_status": previous_status,
            "client_email_sent": False,
        })
        db.commit()
        return {
            "ok": True,
            "archived": False,
            "status": previous_status,
            "message": "Enquiry reopened · no client email sent",
        }

    @app.get("/api/bookings/{booking_id}/reschedule-check")
    def reschedule_check(
        booking_id: str,
        new_date: date = Query(...),
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = db.get(Booking, booking_id)
        if not booking:
            raise HTTPException(404, "Wedding booking not found")
        if booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING:
            raise HTTPException(409, "Only a Weddings By Mark wedding can be moved here")
        contract = db.scalar(select(ContractAcceptance.id).where(
            ContractAcceptance.booking_id == booking.id
        ).limit(1))
        conflicts = _date_conflicts(db, booking, new_date)
        return {
            "current_date": booking.event_date.isoformat() if booking.event_date else None,
            "new_date": new_date.isoformat(),
            "conflicts": conflicts,
            "signed_agreement_retained": bool(contract),
            "no_email_sent": True,
        }

    @app.post("/api/bookings/{booking_id}/reschedule")
    def reschedule_wedding(
        booking_id: str,
        payload: RescheduleWeddingIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = db.scalar(select(Booking).options(
            selectinload(Booking.invoices),
            selectinload(Booking.tasks),
        ).where(Booking.id == booking_id))
        if not booking:
            raise HTTPException(404, "Wedding booking not found")
        if booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING:
            raise HTTPException(409, "Only a Weddings By Mark wedding can be moved here")
        if booking.status not in (RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS):
            raise HTTPException(409, "Only a live booked wedding can use Move wedding date")
        if not booking.event_date:
            raise HTTPException(409, "Add the current wedding date before moving it")
        if payload.new_date == booking.event_date:
            raise HTTPException(422, "Choose a different wedding date")
        if payload.new_date < date.today():
            raise HTTPException(422, "The new wedding date cannot be in the past")
        conflicts = _date_conflicts(db, booking, payload.new_date)
        if conflicts["count"] and not payload.confirm_conflicts:
            raise HTTPException(409, "The new date has another enquiry, booking or private date block. Review and confirm the clash first")

        old_date = booking.event_date
        old_standard_due = old_date - timedelta(days=45)
        active_invoices = [row for row in booking.invoices if row.status not in ("void", "cancelled")]
        agreed_due_dates = {
            row.id: row.due_date
            for row in active_invoices
            if row.due_date and row.due_date != old_standard_due
        }
        signed_agreement = db.scalar(select(ContractAcceptance.id).where(
            ContractAcceptance.booking_id == booking.id
        ).limit(1))

        booking.event_date = payload.new_date
        if not booking.balance_due_date or booking.balance_due_date == old_standard_due:
            booking.balance_due_date = payload.new_date - timedelta(days=45)
        refresh_payment_dates(db, booking)
        for invoice in active_invoices:
            if not invoice.legacy_source:
                invoice.supply_date = payload.new_date
            agreed_due = agreed_due_dates.get(invoice.id)
            if agreed_due:
                invoice.due_date = agreed_due
                schedule = [dict(item) for item in (invoice.payment_schedule or [])]
                for row in schedule:
                    if row.get("key") in ("final_45", "final_75"):
                        row["due_date"] = agreed_due.isoformat()
                invoice.payment_schedule = schedule
                booking.balance_due_date = agreed_due
        sync_final_call_task(db, booking)

        superseded = 0
        for reminder in db.scalars(select(ReminderLog).where(
            ReminderLog.booking_id == booking.id,
            ReminderLog.status.in_(("pending", "failed", "sending")),
        )).all():
            if (
                reminder.reminder_key in ("check_in_120", "check_in_30", "balance_due_7", "balance_due_1")
                or reminder.reminder_key.startswith("balance_overdue_")
            ):
                reminder.status = "superseded"
                reminder.error = "Superseded when the wedding date moved"
                reminder.next_attempt_at = None
                superseded += 1

        agreement_task_created = False
        if signed_agreement and not db.scalar(select(Task.id).where(
            Task.booking_id == booking.id,
            Task.workflow_key == "wbm_reschedule_agreement_review",
            Task.completed.is_(False),
        ).limit(1)):
            db.add(Task(
                booking_id=booking.id,
                title="Review agreement after wedding date change",
                workflow_key="wbm_reschedule_agreement_review",
                due_at=datetime.combine(date.today(), time(9, 0)),
            ))
            agreement_task_created = True

        workflow = dict(booking.workflow_state or {})
        history = list(workflow.get("reschedule_history") or [])
        history.append({
            "old_date": old_date.isoformat(),
            "new_date": payload.new_date.isoformat(),
            "reason": payload.reason.strip(),
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "changed_by": admin.email,
            "conflicts_confirmed": bool(conflicts["count"]),
            "signed_agreement_retained": bool(signed_agreement),
            "client_email_sent": False,
        })
        workflow["reschedule_history"] = history[-20:]
        booking.workflow_state = workflow
        audit(db, "reschedule_wedding", "booking", booking.id, {
            "old_date": old_date.isoformat(),
            "new_date": payload.new_date.isoformat(),
            "reason": payload.reason.strip(),
            "conflict_count": conflicts["count"],
            "invoice_numbers_retained": [row.number for row in active_invoices],
            "signed_agreement_retained": bool(signed_agreement),
            "agreement_review_task_created": agreement_task_created,
            "superseded_reminders": superseded,
            "client_email_sent": False,
        })
        db.commit()
        calendar = sync_booking_calendar_safely(db, booking)
        return {
            "ok": True,
            "old_date": old_date.isoformat(),
            "new_date": payload.new_date.isoformat(),
            "conflicts_confirmed": bool(conflicts["count"]),
            "signed_agreement_retained": bool(signed_agreement),
            "agreement_review_task_created": agreement_task_created,
            "calendar_status": calendar.get("status"),
            "message": "Wedding date moved safely · no client email sent",
        }

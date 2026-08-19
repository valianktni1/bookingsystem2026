"""Version 8.2: safe cancellation, voiding, resets and permanent deletion.

This module is intentionally self-contained so the V8.2 update can be added
without restructuring the existing application.
"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .google_calendar import sync_booking_calendar_safely
from .models import (
    Admin,
    AuditLog,
    Booking,
    BookingNote,
    Client,
    ClientPortalToken,
    ContractAcceptance,
    Document,
    EmailLog,
    FormSubmission,
    Invoice,
    Payment,
    Quote,
    RecordStatus,
    ReminderLog,
    Task,
)
from .security import current_admin
from .services import audit

settings = get_settings()


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class CancelBookingIn(ReasonIn):
    cancellation_date: date = Field(default_factory=date.today)


class RefundIn(ReasonIn):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    refund_date: date = Field(default_factory=date.today)
    reference: str | None = Field(default=None, max_length=120)


class ConfirmedDeleteIn(ReasonIn):
    confirmation: str = Field(min_length=3, max_length=300)


def _reason(payload: ReasonIn) -> str:
    reason = payload.reason.strip()
    if len(reason) < 3:
        raise HTTPException(422, "Please enter a clear reason")
    return reason


def _booking(db: Session, booking_id: str) -> Booking:
    row = db.get(Booking, booking_id)
    if not row:
        raise HTTPException(404, "Record not found")
    return row


def _invoice(db: Session, invoice_id: str) -> Invoice:
    row = db.get(Invoice, invoice_id)
    if not row:
        raise HTTPException(404, "Invoice not found")
    return row


def _append_invoice_cancellation_note(invoice: Invoice, *, now: datetime,
                                      cancellation_date: date, admin_email: str,
                                      reason: str, closed_balance: Decimal) -> None:
    marker = (
        f"CANCELLED {now.isoformat()} by {admin_email}. "
        f"Cancellation date: {cancellation_date.isoformat()}. "
        f"Unpaid balance closed: £{closed_balance.quantize(Decimal('0.01'))}. "
        f"Reason: {reason}"
    )
    invoice.notes = f"{invoice.notes.rstrip()}\n\n{marker}" if invoice.notes else marker


def _live_invoice_status(invoice: Invoice) -> str:
    paid = Decimal(invoice.paid or 0)
    total = Decimal(invoice.total or 0)
    if paid >= total:
        return "paid"
    if paid > 0:
        return "part_paid"
    return "unpaid"


def register_v82_routes(app: FastAPI) -> None:
    @app.post("/api/bookings/{booking_id}/cancel")
    def cancel_booking(
        booking_id: str,
        payload: CancelBookingIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = _booking(db, booking_id)
        if booking.status == RecordStatus.CANCELLED:
            raise HTTPException(409, "This record is already cancelled")
        if payload.cancellation_date > date.today():
            raise HTTPException(422, "The cancellation date cannot be in the future")

        reason = _reason(payload)
        now = datetime.now(timezone.utc)
        open_tasks = db.scalars(
            select(Task).where(Task.booking_id == booking.id, Task.completed.is_(False))
        ).all()
        open_task_ids = [task.id for task in open_tasks]
        for task in open_tasks:
            task.completed = True

        tokens = db.scalars(
            select(ClientPortalToken).where(
                ClientPortalToken.booking_id == booking.id,
                ClientPortalToken.revoked_at.is_(None),
            )
        ).all()
        for token in tokens:
            token.revoked_at = now

        invoices = db.scalars(
            select(Invoice).where(Invoice.booking_id == booking.id)
        ).all()
        invoice_states = []
        total_closed = Decimal("0")
        total_retained = Decimal("0")
        for invoice in invoices:
            paid = Decimal(invoice.paid or 0)
            total_retained += paid
            if invoice.status == "void":
                invoice_states.append({
                    "invoice_id": invoice.id,
                    "number": invoice.number,
                    "previous_status": "void",
                    "closed_balance": 0,
                })
                continue
            closed_balance = max(Decimal("0"), Decimal(invoice.total or 0) - paid)
            total_closed += closed_balance
            invoice_states.append({
                "invoice_id": invoice.id,
                "number": invoice.number,
                "previous_status": invoice.status,
                "closed_balance": float(closed_balance),
                "retained_paid": float(paid),
            })
            invoice.status = "cancelled"
            _append_invoice_cancellation_note(
                invoice,
                now=now,
                cancellation_date=payload.cancellation_date,
                admin_email=admin.email,
                reason=reason,
                closed_balance=closed_balance,
            )

        workflow = dict(booking.workflow_state or {})
        workflow["cancellation"] = {
            "cancelled_at": now.isoformat(),
            "cancellation_date": payload.cancellation_date.isoformat(),
            "reason": reason,
            "cancelled_by": admin.email,
            "previous_status": booking.status.value,
            "previous_automation_suppressed": booking.automation_suppressed,
            "open_task_ids": open_task_ids,
            "revoked_portal_links": len(tokens),
            "invoice_states": invoice_states,
            "unpaid_balance_closed": float(total_closed),
            "payments_retained": float(total_retained),
            "emails_sent": 0,
        }
        booking.workflow_state = workflow
        booking.status = RecordStatus.CANCELLED
        booking.automation_suppressed = True
        db.add(BookingNote(
            booking_id=booking.id,
            body=(f"Booking cancelled on {payload.cancellation_date.strftime('%d %B %Y')}. "
                  f"Unpaid balance closed: £{total_closed:,.2f}. "
                  f"Payments retained: £{total_retained:,.2f}. Reason: {reason}"),
        ))
        audit(
            db,
            "cancel_booking",
            "booking",
            booking.id,
            {"reason": reason,
             "cancellation_date": payload.cancellation_date.isoformat(),
             "revoked_portal_links": len(tokens),
             "unpaid_balance_closed": float(total_closed),
             "payments_retained": float(total_retained),
             "emails_sent": 0},
        )
        db.commit()
        calendar_sync = sync_booking_calendar_safely(db, booking)
        return {
            "ok": True,
            "status": booking.status.value,
            "revoked_portal_links": len(tokens),
            "unpaid_balance_closed": float(total_closed),
            "payments_retained": float(total_retained),
            "emails_sent": 0,
            "google_calendar": calendar_sync,
            "message": ("Booking cancelled and the unpaid balance was closed. "
                        "All invoice numbers and recorded payments were retained. No client email was sent."),
        }

    @app.post("/api/bookings/{booking_id}/reopen")
    def reopen_booking(
        booking_id: str,
        payload: ReasonIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = _booking(db, booking_id)
        if booking.status != RecordStatus.CANCELLED:
            raise HTTPException(409, "Only a cancelled record can be reopened")

        reason = _reason(payload)
        workflow = dict(booking.workflow_state or {})
        cancellation = dict(workflow.get("cancellation") or {})
        previous_value = cancellation.get("previous_status") or RecordStatus.ENQUIRY.value
        try:
            previous_status = RecordStatus(previous_value)
        except ValueError:
            previous_status = RecordStatus.ENQUIRY
        if previous_status == RecordStatus.CANCELLED:
            previous_status = RecordStatus.ENQUIRY

        open_task_ids = list(cancellation.get("open_task_ids") or [])
        if open_task_ids:
            tasks = db.scalars(
                select(Task).where(Task.booking_id == booking.id, Task.id.in_(open_task_ids))
            ).all()
            for task in tasks:
                task.completed = False

        invoice_states = {
            row.get("invoice_id"): row
            for row in (cancellation.get("invoice_states") or [])
            if isinstance(row, dict) and row.get("invoice_id")
        }
        for invoice in db.scalars(select(Invoice).where(Invoice.booking_id == booking.id)).all():
            state = invoice_states.get(invoice.id)
            if invoice.status != "cancelled" or not state:
                continue
            if state.get("previous_status") == "void":
                invoice.status = "void"
            else:
                invoice.status = _live_invoice_status(invoice)

        cancellation.update(
            {
                "reopened_at": datetime.now(timezone.utc).isoformat(),
                "reopened_by": admin.email,
                "reopen_reason": reason,
            }
        )
        history = list(workflow.get("cancellation_history") or [])
        history.append(cancellation)
        workflow["cancellation_history"] = history[-20:]
        workflow.pop("cancellation", None)
        booking.workflow_state = workflow
        booking.status = previous_status
        booking.automation_suppressed = bool(
            cancellation.get("previous_automation_suppressed", booking.legacy_source == "studio_ninja")
        )
        audit(db, "reopen_booking", "booking", booking.id, {"reason": reason})
        db.commit()
        calendar_sync = sync_booking_calendar_safely(db, booking)
        return {
            "ok": True,
            "status": booking.status.value,
            "google_calendar": calendar_sync,
            "message": "Record reopened. Create a new client portal link if one is needed.",
        }

    @app.post("/api/invoices/{invoice_id}/refunds", status_code=201)
    def record_cancelled_invoice_refund(
        invoice_id: str,
        payload: RefundIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        invoice = _invoice(db, invoice_id)
        booking = _booking(db, invoice.booking_id)
        if booking.status != RecordStatus.CANCELLED or invoice.status != "cancelled":
            raise HTTPException(409, "Refunds here are only for a cancelled booking invoice")
        if payload.refund_date > date.today():
            raise HTTPException(422, "The refund date cannot be in the future")
        available = Decimal(invoice.paid or 0)
        if payload.amount > available:
            raise HTTPException(422, "Refund cannot exceed the payment currently retained")

        reason = _reason(payload)
        refund = Payment(
            invoice_id=invoice.id,
            amount=-payload.amount,
            paid_date=payload.refund_date,
            payment_type="refund",
            reference=payload.reference or f"Refund {invoice.number}",
            notes=reason,
        )
        db.add(refund)
        invoice.paid = available - payload.amount

        workflow = dict(booking.workflow_state or {})
        cancellation = dict(workflow.get("cancellation") or {})
        refunds = list(cancellation.get("refunds") or [])
        refunds.append({
            "invoice_id": invoice.id,
            "invoice_number": invoice.number,
            "amount": float(payload.amount),
            "refund_date": payload.refund_date.isoformat(),
            "reason": reason,
            "reference": refund.reference,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "recorded_by": admin.email,
        })
        cancellation["refunds"] = refunds[-100:]
        cancellation["payments_retained"] = float(sum(
            Decimal(row.paid or 0)
            for row in db.scalars(select(Invoice).where(Invoice.booking_id == booking.id)).all()
        ))
        workflow["cancellation"] = cancellation
        booking.workflow_state = workflow
        db.add(BookingNote(
            booking_id=booking.id,
            body=(f"Refund of £{payload.amount:,.2f} recorded against {invoice.number} "
                  f"on {payload.refund_date.strftime('%d %B %Y')}. Reason: {reason}"),
        ))
        audit(db, "record_cancellation_refund", "booking", booking.id, {
            "invoice_id": invoice.id,
            "invoice_number": invoice.number,
            "amount": float(payload.amount),
            "refund_date": payload.refund_date.isoformat(),
            "reason": reason,
            "reference": refund.reference,
            "emails_sent": 0,
        })
        db.commit()
        return {
            "ok": True,
            "invoice_id": invoice.id,
            "refund_id": refund.id,
            "refund_amount": float(payload.amount),
            "payments_retained": float(invoice.paid),
            "emails_sent": 0,
            "message": "Refund recorded. The cancelled booking remains closed and no client email was sent.",
        }

    @app.post("/api/bookings/{booking_id}/contract/reset")
    def reset_contract_acceptance(
        booking_id: str,
        payload: ReasonIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = _booking(db, booking_id)
        row = db.scalar(
            select(ContractAcceptance).where(ContractAcceptance.booking_id == booking.id)
        )
        if not row:
            raise HTTPException(404, "There is no accepted agreement to reset")

        reason = _reason(payload)
        accepted_at = row.accepted_at.isoformat()
        contract_version = row.contract_version
        db.delete(row)
        tasks = db.scalars(
            select(Task).where(
                Task.booking_id == booking.id,
                Task.title.ilike("%contract%"),
            )
        ).all()
        for task in tasks:
            task.completed = False
        audit(
            db,
            "reset_contract_acceptance",
            "booking",
            booking.id,
            {
                "reason": reason,
                "contract_version": contract_version,
                "originally_accepted_at": accepted_at,
                "admin": admin.email,
            },
        )
        db.commit()
        return {"ok": True, "message": "Agreement acceptance reset"}

    @app.post("/api/bookings/{booking_id}/forms/{form_type}/reset")
    def reset_submitted_form(
        booking_id: str,
        form_type: str,
        payload: ReasonIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        allowed = {"booking_form", "final_questionnaire"}
        if form_type not in allowed:
            raise HTTPException(422, "That form type cannot be reset")
        booking = _booking(db, booking_id)
        row = db.scalar(
            select(FormSubmission).where(
                FormSubmission.booking_id == booking.id,
                FormSubmission.form_type == form_type,
            )
        )
        if not row:
            raise HTTPException(404, "That form has not been submitted")

        reason = _reason(payload)
        submitted_at = row.submitted_at.isoformat()
        db.delete(row)
        if form_type == "booking_form":
            existing = dict(booking.form_data or {})
            booking.form_data = (
                {"website_enquiry": existing["website_enquiry"]}
                if "website_enquiry" in existing
                else {}
            )
            pattern = "%booking form%"
        else:
            workflow = dict(booking.workflow_state or {})
            workflow.pop("final_questionnaire", None)
            booking.workflow_state = workflow
            pattern = "%questionnaire%"

        tasks = db.scalars(
            select(Task).where(Task.booking_id == booking.id, Task.title.ilike(pattern))
        ).all()
        for task in tasks:
            task.completed = False
        audit(
            db,
            "reset_submitted_form",
            "booking",
            booking.id,
            {
                "form_type": form_type,
                "reason": reason,
                "originally_submitted_at": submitted_at,
                "admin": admin.email,
            },
        )
        db.commit()
        return {"ok": True, "message": "Submitted form reset"}

    @app.post("/api/invoices/{invoice_id}/void")
    def void_invoice(
        invoice_id: str,
        payload: ReasonIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        invoice = _invoice(db, invoice_id)
        if invoice.status == "void":
            raise HTTPException(409, "This invoice is already void")
        if invoice.status == "cancelled":
            raise HTTPException(409, "This invoice is already closed by the booking cancellation")

        reason = _reason(payload)
        old_status = invoice.status
        now = datetime.now(timezone.utc)
        marker = (
            f"VOIDED {now.strftime('%d %B %Y %H:%M UTC')} by {admin.email}. "
            f"Reason: {reason}"
        )
        invoice.notes = f"{invoice.notes}\n\n{marker}".strip() if invoice.notes else marker
        invoice.status = "void"
        audit(
            db,
            "void_invoice",
            "booking",
            invoice.booking_id,
            {
                "invoice": invoice.number,
                "reason": reason,
                "previous_status": old_status,
                "paid": float(invoice.paid or 0),
            },
        )
        db.commit()
        return {
            "ok": True,
            "number": invoice.number,
            "status": invoice.status,
            "message": "Invoice voided. Its number and payment history were retained.",
        }

    @app.post("/api/invoices/{invoice_id}/permanent-delete")
    def permanently_delete_invoice(
        invoice_id: str,
        payload: ConfirmedDeleteIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        invoice = _invoice(db, invoice_id)
        if invoice.legacy_source == "studio_ninja":
            raise HTTPException(409, "Imported Studio Ninja invoices are retained and can only be voided")
        required = f"DELETE {invoice.number}"
        if payload.confirmation.strip() != required:
            raise HTTPException(422, f"Type {required} exactly to confirm")
        reason = _reason(payload)

        payment_count = db.scalar(
            select(Payment.id).where(Payment.invoice_id == invoice.id).limit(1)
        )
        if payment_count or Decimal(invoice.paid or 0) > 0:
            raise HTTPException(
                409,
                "This invoice has payment history and cannot be deleted. Void it instead.",
            )
        if invoice.status != "unpaid":
            raise HTTPException(
                409,
                "Only an unpaid mistaken invoice can be deleted. Void this invoice instead.",
            )
        if db.scalar(select(Quote.id).where(Quote.invoice_id == invoice.id).limit(1)):
            raise HTTPException(
                409,
                "This invoice belongs to an accepted package quote and must be voided, not deleted.",
            )

        number = invoice.number
        booking_id = invoice.booking_id
        audit(
            db,
            "delete_mistaken_invoice",
            "booking",
            booking_id,
            {"invoice": number, "reason": reason, "admin": admin.email},
        )
        db.delete(invoice)
        db.commit()
        return {"ok": True, "number": number, "message": "Mistaken invoice deleted"}

    @app.post("/api/bookings/{booking_id}/permanent-delete")
    def permanently_delete_booking(
        booking_id: str,
        payload: ConfirmedDeleteIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = _booking(db, booking_id)
        if booking.legacy_source == "studio_ninja":
            raise HTTPException(409, "Imported Studio Ninja records are retained; cancel and archive them instead")
        required = f"DELETE {booking.title}"
        if payload.confirmation.strip() != required:
            raise HTTPException(422, f"Type {required} exactly to confirm")
        reason = _reason(payload)

        invoices = db.scalars(select(Invoice).where(Invoice.booking_id == booking.id)).all()
        invoice_ids = [invoice.id for invoice in invoices]
        has_payments = False
        if invoice_ids:
            has_payments = bool(
                db.scalar(select(Payment.id).where(Payment.invoice_id.in_(invoice_ids)).limit(1))
            )
        has_payments = has_payments or any(Decimal(invoice.paid or 0) > 0 for invoice in invoices)
        if has_payments and not booking.is_test:
            raise HTTPException(
                409,
                "This record has payment history and cannot be permanently deleted. Cancel and archive it instead.",
            )
        # A deliberately confirmed test/duplicate may contain an accepted
        # quote and a voided zero-payment invoice. Its invoice number remains
        # consumed by the counter, but the false client record may be removed.
        if (not booking.is_test
                and any(invoice.status not in ("unpaid", "void") for invoice in invoices)):
            raise HTTPException(
                409,
                "This record contains a retained financial invoice and cannot be permanently deleted. Cancel and archive it instead.",
            )

        client_id = booking.client_id
        brand_value = booking.brand.value
        kind_value = booking.kind.value
        counts = {
            "invoices": len(invoices),
            "tasks": db.scalar(select(Task.id).where(Task.booking_id == booking.id).limit(1)) is not None,
            "documents": db.scalar(select(Document.id).where(Document.booking_id == booking.id).limit(1)) is not None,
            "contract": db.scalar(select(ContractAcceptance.id).where(ContractAcceptance.booking_id == booking.id).limit(1)) is not None,
        }

        if invoice_ids:
            db.execute(delete(Payment).where(Payment.invoice_id.in_(invoice_ids)))
        db.execute(delete(Quote).where(Quote.booking_id == booking.id))
        db.execute(delete(Invoice).where(Invoice.booking_id == booking.id))
        db.execute(delete(Task).where(Task.booking_id == booking.id))
        db.execute(delete(Document).where(Document.booking_id == booking.id))
        db.execute(delete(BookingNote).where(BookingNote.booking_id == booking.id))
        db.execute(delete(ClientPortalToken).where(ClientPortalToken.booking_id == booking.id))
        db.execute(delete(FormSubmission).where(FormSubmission.booking_id == booking.id))
        db.execute(delete(ContractAcceptance).where(ContractAcceptance.booking_id == booking.id))
        db.execute(delete(EmailLog).where(EmailLog.booking_id == booking.id))
        db.execute(delete(ReminderLog).where(ReminderLog.booking_id == booking.id))
        db.execute(delete(AuditLog).where(AuditLog.entity_id == booking.id))
        db.execute(delete(Booking).where(Booking.id == booking.id))

        another_booking = db.scalar(
            select(Booking.id).where(Booking.client_id == client_id).limit(1)
        )
        if not another_booking:
            db.execute(delete(Client).where(Client.id == client_id))

        db.add(
            AuditLog(
                action="permanently_delete_booking",
                entity_type="deleted_booking",
                entity_id=None,
                details={
                    "deleted_booking_id": booking_id,
                    "brand": brand_value,
                    "kind": kind_value,
                    "reason": reason,
                    "admin": admin.email,
                    "deleted_children": counts,
                },
            )
        )
        db.commit()
        shutil.rmtree(settings.storage_root / booking_id, ignore_errors=True)
        return {"ok": True, "message": "Record and its removable linked data were permanently deleted"}

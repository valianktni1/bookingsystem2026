"""Version 8.2: safe cancellation, voiding, resets and permanent deletion.

This module is intentionally self-contained so the V8.2 update can be added
without restructuring the existing application.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
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


def register_v82_routes(app: FastAPI) -> None:
    @app.post("/api/bookings/{booking_id}/cancel")
    def cancel_booking(
        booking_id: str,
        payload: ReasonIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = _booking(db, booking_id)
        if booking.status == RecordStatus.CANCELLED:
            raise HTTPException(409, "This record is already cancelled")

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

        workflow = dict(booking.workflow_state or {})
        workflow["cancellation"] = {
            "cancelled_at": now.isoformat(),
            "reason": reason,
            "cancelled_by": admin.email,
            "previous_status": booking.status.value,
            "open_task_ids": open_task_ids,
            "revoked_portal_links": len(tokens),
        }
        booking.workflow_state = workflow
        booking.status = RecordStatus.CANCELLED
        audit(
            db,
            "cancel_booking",
            "booking",
            booking.id,
            {"reason": reason, "revoked_portal_links": len(tokens)},
        )
        db.commit()
        return {
            "ok": True,
            "status": booking.status.value,
            "revoked_portal_links": len(tokens),
            "message": "Record cancelled. Existing invoices were retained and can be voided separately.",
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
        audit(db, "reopen_booking", "booking", booking.id, {"reason": reason})
        db.commit()
        return {
            "ok": True,
            "status": booking.status.value,
            "message": "Record reopened. Create a new client portal link if one is needed.",
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

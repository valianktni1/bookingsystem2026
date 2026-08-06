"""Protected import endpoints for the complete Studio Ninja archive batch.

Archive imports preserve the original invoice numbers and never advance the
live Weddings By Mark or Ivory Digital invoice counters.  They deliberately
cannot create portal links, send emails, schedule reminders or touch Google
Calendar.  Every imported record remains permanently automation-suppressed.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    Admin,
    Booking,
    Brand,
    Client,
    ContractAcceptance,
    FormSubmission,
    Invoice,
    Payment,
    Quote,
    RecordKind,
    RecordStatus,
)
from .security import current_admin
from .services import audit


ARCHIVE_CONFIRMATION = "IMPORT ARCHIVE WITHOUT EMAILS"


class ArchiveClientIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    partner_name: str | None = Field(default=None, max_length=160)
    company_name: str | None = Field(default=None, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=2000)


class ArchivePaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_date: date
    payment_type: str = Field(default="bank_transfer", max_length=40)
    reference: str | None = Field(default=None, max_length=120)
    legacy_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


class ArchiveScheduleIn(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(ge=0)
    due_date: date | None = None
    status: str = Field(default="scheduled", max_length=40)


class ArchiveInvoiceIn(BaseModel):
    number: str = Field(min_length=1, max_length=30)
    sequence: int = Field(le=2000)
    legacy_number: str = Field(min_length=1, max_length=80)
    legacy_quote_number: str | None = Field(default=None, max_length=80)
    issue_date: date
    deposit_due_date: date | None = None
    supply_date: date | None = None
    due_date: date | None = None
    description: str | None = Field(default=None, max_length=5000)
    total: Decimal = Field(ge=0)
    paid: Decimal = Field(ge=0)
    status: Literal["paid", "part_paid", "unpaid", "void"]
    notes: str | None = Field(default=None, max_length=5000)
    line_items: list[dict] = Field(default_factory=list, max_length=100)
    payment_schedule: list[ArchiveScheduleIn] = Field(default_factory=list, max_length=50)
    payments: list[ArchivePaymentIn] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def financial_values_are_consistent(self):
        if self.paid > self.total:
            raise ValueError("Imported paid total cannot exceed the invoice total")
        itemised = sum((row.amount for row in self.payments), Decimal("0"))
        if itemised > self.paid:
            raise ValueError("Itemised imported payments cannot exceed the paid summary")
        if self.number != self.legacy_number:
            raise ValueError("Archive invoices must retain their original Studio Ninja number")
        return self


class ArchiveQuoteIn(BaseModel):
    legacy_number: str | None = Field(default=None, max_length=80)
    status: Literal["accepted", "declined", "draft"] = "accepted"
    accepted_at: datetime | None = None
    created_at: datetime | None = None
    linked_invoice_number: str | None = Field(default=None, max_length=30)
    line_items: list[dict] = Field(default_factory=list, max_length=100)
    total: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)


class ArchiveFormIn(BaseModel):
    data: dict
    submitted_at: datetime


class ArchiveContractIn(BaseModel):
    accepted_at: datetime
    accepted_name: str = Field(min_length=2, max_length=180)
    accepted_email: EmailStr
    contract_title: str = Field(default="Studio Ninja wedding contract", max_length=180)
    contract_version: str = Field(default="Legacy archive import", max_length=60)
    contract_body: str = Field(
        default="The original Studio Ninja contract PDF is retained with this record.",
        max_length=50000,
    )
    date_source: Literal[
        "questionnaire_completed_date",
        "earliest_deposit_payment_date",
        "manual_review",
    ]
    source_detail: str | None = Field(default=None, max_length=500)


class ArchiveRecordIn(BaseModel):
    legacy_id: str = Field(min_length=1, max_length=120)
    import_batch: str = Field(min_length=1, max_length=120)
    brand: Brand
    kind: RecordKind
    title: str = Field(min_length=1, max_length=200)
    status: RecordStatus
    archived: bool = True
    source_created_at: datetime | None = None
    event_date: date | None = None
    venue_or_project: str | None = Field(default=None, max_length=240)
    venue_address: str | None = Field(default=None, max_length=2000)
    package_name: str | None = Field(default=None, max_length=160)
    quoted_total: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    balance_due_date: date | None = None
    notes: str | None = Field(default=None, max_length=10000)
    client: ArchiveClientIn
    invoices: list[ArchiveInvoiceIn] = Field(default_factory=list, max_length=50)
    quotes: list[ArchiveQuoteIn] = Field(default_factory=list, max_length=20)
    booking_form: ArchiveFormIn | None = None
    final_questionnaire: ArchiveFormIn | None = None
    contract: ArchiveContractIn | None = None
    legacy_timeline: list[dict] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def archive_identifiers_are_safe(self):
        numbers = [row.number for row in self.invoices]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Archive invoice numbers must be unique within each record")
        if self.brand == Brand.WBM and self.kind == RecordKind.DIGITAL:
            raise ValueError("A Weddings By Mark record cannot use the digital project kind")
        return self


class ArchiveImportRequest(BaseModel):
    confirmation: str
    record: ArchiveRecordIn


def _confirm(value: str) -> None:
    if value.strip() != ARCHIVE_CONFIRMATION:
        raise HTTPException(422, f"Type {ARCHIVE_CONFIRMATION} exactly to confirm")


def _existing_booking(db: Session, legacy_id: str) -> Booking | None:
    return db.scalar(select(Booking).where(
        Booking.legacy_source == "studio_ninja",
        Booking.legacy_id == legacy_id,
    ))


def _invoice_conflicts(db: Session, numbers: list[str]) -> list[str]:
    if not numbers:
        return []
    return list(db.scalars(select(Invoice.number).where(Invoice.number.in_(numbers))).all())


def register_legacy_archive_import_routes(app: FastAPI) -> None:
    @app.get("/api/legacy-import/archive/readiness")
    def archive_readiness(
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        return {
            "mode": "protected_archive_no_email",
            "confirmation": ARCHIVE_CONFIRMATION,
            "archive_records": db.scalar(select(func.count()).select_from(Booking).where(
                Booking.legacy_import_batch == "studio-ninja-complete-archive-2026-08-06"
            )) or 0,
            "all_studio_ninja_records": db.scalar(select(func.count()).select_from(Booking).where(
                Booking.legacy_source == "studio_ninja"
            )) or 0,
            "emails_will_be_sent": False,
            "reminders_will_run": False,
            "portal_links_will_be_created": False,
            "calendar_will_be_contacted": False,
            "live_invoice_counters_will_change": False,
        }

    @app.post("/api/legacy-import/archive/validate")
    def validate_archive_record(
        payload: ArchiveImportRequest,
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        _confirm(payload.confirmation)
        existing = _existing_booking(db, payload.record.legacy_id)
        if existing:
            return {
                "valid": False,
                "duplicate": True,
                "existing_booking_id": existing.id,
                "invoice_conflicts": [],
                "emails_will_be_sent": False,
            }
        conflicts = _invoice_conflicts(db, [row.number for row in payload.record.invoices])
        return {
            "valid": not conflicts,
            "duplicate": False,
            "existing_booking_id": None,
            "invoice_conflicts": conflicts,
            "invoice_count": len(payload.record.invoices),
            "payment_count": sum(len(row.payments) for row in payload.record.invoices),
            "emails_will_be_sent": False,
            "reminders_will_run": False,
            "portal_links_will_be_created": False,
            "live_invoice_counters_will_change": False,
        }

    @app.post("/api/legacy-import/archive/records", status_code=201)
    def import_archive_record(
        payload: ArchiveImportRequest,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        _confirm(payload.confirmation)
        source = payload.record
        existing = _existing_booking(db, source.legacy_id)
        if existing:
            raise HTTPException(409, f"This Studio Ninja record is already linked to {existing.id}")
        conflicts = _invoice_conflicts(db, [row.number for row in source.invoices])
        if conflicts:
            raise HTTPException(409, f"Original invoice number already exists: {', '.join(conflicts)}")

        try:
            created_at = source.source_created_at or datetime.now(timezone.utc)
            client = Client(
                first_name=source.client.first_name.strip(),
                last_name=source.client.last_name.strip(),
                partner_name=source.client.partner_name,
                company_name=source.client.company_name,
                email=str(source.client.email).lower(),
                phone=source.client.phone,
                address=source.client.address,
                created_at=created_at,
            )
            db.add(client)
            db.flush()

            all_payments = [payment for invoice in source.invoices for payment in invoice.payments]
            first_paid = min((row.paid_date for row in all_payments), default=None)
            workflow_state = {
                "source": "studio_ninja_complete_archive_import",
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "imported_by": admin.email,
                "legacy_timeline": source.legacy_timeline,
                "archive_import": source.archived,
                "final_details_manual_unlock": False,
            }
            booking = Booking(
                brand=source.brand,
                kind=source.kind,
                status=source.status,
                title=source.title,
                client_id=client.id,
                event_date=source.event_date,
                venue_or_project=source.venue_or_project,
                venue_address=source.venue_address,
                package_name=source.package_name,
                quoted_total=source.quoted_total,
                deposit_amount=source.deposit_amount,
                deposit_paid_date=first_paid,
                balance_due_date=source.balance_due_date,
                notes=source.notes,
                form_data=source.booking_form.data if source.booking_form else {},
                workflow_state=workflow_state,
                legacy_source="studio_ninja",
                legacy_id=source.legacy_id,
                legacy_import_batch=source.import_batch,
                automation_suppressed=True,
                created_at=created_at,
                updated_at=created_at,
                archived_at=datetime.now(timezone.utc) if source.archived else None,
            )
            db.add(booking)
            db.flush()

            invoices_by_number: dict[str, Invoice] = {}
            for row in source.invoices:
                invoice = Invoice(
                    booking_id=booking.id,
                    brand=source.brand,
                    sequence=row.sequence,
                    number=row.number,
                    issue_date=row.issue_date,
                    deposit_due_date=row.deposit_due_date,
                    supply_date=row.supply_date or source.event_date,
                    due_date=row.due_date,
                    description=row.description,
                    total=row.total,
                    paid=row.paid,
                    status=row.status,
                    notes=row.notes,
                    line_items=row.line_items,
                    payment_schedule=[item.model_dump(mode="json") for item in row.payment_schedule],
                    legacy_number=row.legacy_number,
                    legacy_quote_number=row.legacy_quote_number,
                    legacy_source="studio_ninja",
                    created_at=datetime.combine(row.issue_date, datetime.min.time(), timezone.utc),
                )
                db.add(invoice)
                db.flush()
                invoices_by_number[row.number] = invoice
                for payment_row in row.payments:
                    db.add(Payment(
                        invoice_id=invoice.id,
                        amount=payment_row.amount,
                        paid_date=payment_row.paid_date,
                        payment_type=payment_row.payment_type,
                        reference=payment_row.reference,
                        notes=payment_row.notes,
                        legacy_source="studio_ninja",
                        legacy_reference=payment_row.legacy_reference,
                    ))

            for row in source.quotes:
                linked = invoices_by_number.get(row.linked_invoice_number or "")
                db.add(Quote(
                    booking_id=booking.id,
                    status=row.status,
                    line_items=row.line_items,
                    total=row.total,
                    deposit_amount=row.deposit_amount,
                    invoice_id=linked.id if linked else None,
                    accepted_at=row.accepted_at,
                    legacy_number=row.legacy_number,
                    legacy_source="studio_ninja",
                    created_at=row.created_at or created_at,
                ))

            if source.booking_form:
                db.add(FormSubmission(
                    booking_id=booking.id,
                    form_type="booking_form",
                    data=source.booking_form.data,
                    submitted_at=source.booking_form.submitted_at,
                    updated_at=source.booking_form.submitted_at,
                    submission_source="studio_ninja_questionnaire",
                ))
            if source.final_questionnaire:
                db.add(FormSubmission(
                    booking_id=booking.id,
                    form_type="final_questionnaire",
                    data=source.final_questionnaire.data,
                    submitted_at=source.final_questionnaire.submitted_at,
                    updated_at=source.final_questionnaire.submitted_at,
                    submission_source="studio_ninja_questionnaire",
                ))

            contract = source.contract
            if contract and contract.date_source != "manual_review":
                db.add(ContractAcceptance(
                    booking_id=booking.id,
                    contract_title=contract.contract_title,
                    contract_version=contract.contract_version,
                    contract_body=contract.contract_body,
                    accepted_name=contract.accepted_name,
                    accepted_email=str(contract.accepted_email).lower(),
                    accepted_at=contract.accepted_at,
                    acceptance_source=contract.date_source,
                    source_detail=(contract.source_detail
                                   or "Imported from Studio Ninja; original contract PDF retained"),
                    is_legacy_import=True,
                ))
            elif contract:
                workflow_state["contract_review_required"] = True
                booking.workflow_state = workflow_state

            audit(db, "legacy_archive_import_record", "booking", booking.id, {
                "source": "studio_ninja",
                "legacy_id": source.legacy_id,
                "batch": source.import_batch,
                "archived": source.archived,
                "original_invoice_numbers": [row.number for row in source.invoices],
                "invoices": len(source.invoices),
                "payments": len(all_payments),
                "emails_sent": False,
                "portal_links_created": False,
                "calendar_contacted": False,
                "invoice_counters_changed": False,
                "automation_suppressed": True,
            })
            db.commit()
        except Exception:
            db.rollback()
            raise

        return {
            "ok": True,
            "booking_id": booking.id,
            "invoice_numbers": [row.number for row in source.invoices],
            "emails_sent": False,
            "portal_links_created": False,
            "calendar_contacted": False,
            "invoice_counters_changed": False,
            "automation_suppressed": True,
            "message": "Archive imported safely with all client automation paused",
        }

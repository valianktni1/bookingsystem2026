"""Protected Studio Ninja legacy-import endpoints.

These endpoints deliberately never issue portal links, send email, or run
reminders. Imported records remain automation-suppressed until Mark activates
them from the record after checking the migrated information.
"""

from __future__ import annotations

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
    InvoiceCounter,
    Payment,
    Quote,
    RecordKind,
    RecordStatus,
    Task,
)
from .security import current_admin
from .services import audit, invoice_status, next_invoice_number


class LegacyClientIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    partner_name: str | None = Field(default=None, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=2000)


class LegacyPaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_date: date
    payment_type: str = Field(default="bank_transfer", max_length=40)
    reference: str | None = Field(default=None, max_length=120)
    legacy_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


class LegacyScheduleIn(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(ge=0)
    due_date: date | None = None
    status: str = Field(default="scheduled", max_length=40)


class LegacyInvoiceIn(BaseModel):
    legacy_number: str = Field(min_length=1, max_length=80)
    legacy_quote_number: str | None = Field(default=None, max_length=80)
    issue_date: date
    deposit_due_date: date | None = None
    supply_date: date | None = None
    due_date: date | None = None
    description: str | None = Field(default=None, max_length=5000)
    total: Decimal = Field(gt=0)
    notes: str | None = Field(default=None, max_length=5000)
    line_items: list[dict] = Field(default_factory=list, max_length=100)
    payment_schedule: list[LegacyScheduleIn] = Field(default_factory=list, max_length=50)
    payments: list[LegacyPaymentIn] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def payments_do_not_exceed_total(self):
        if sum((row.amount for row in self.payments), Decimal("0")) > self.total:
            raise ValueError("Imported payments cannot exceed the invoice total")
        return self


class LegacyQuoteIn(BaseModel):
    legacy_number: str | None = Field(default=None, max_length=80)
    accepted_at: datetime
    line_items: list[dict] = Field(default_factory=list, max_length=100)
    total: Decimal = Field(gt=0)
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)


class LegacyFormIn(BaseModel):
    data: dict
    submitted_at: datetime


class LegacyContractIn(BaseModel):
    accepted_at: datetime
    accepted_name: str = Field(min_length=2, max_length=180)
    accepted_email: EmailStr
    contract_title: str = Field(default="Studio Ninja wedding contract", max_length=180)
    contract_version: str = Field(default="Legacy import", max_length=60)
    contract_body: str = Field(
        default="The original Studio Ninja contract PDF is retained with this booking.",
        max_length=50000,
    )
    date_source: Literal[
        "questionnaire_completed_date",
        "earliest_deposit_payment_date",
        "manual_review",
    ]
    source_detail: str | None = Field(default=None, max_length=500)


class LegacyRecordIn(BaseModel):
    legacy_id: str = Field(min_length=1, max_length=120)
    import_batch: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    status: RecordStatus = RecordStatus.CONFIRMED
    event_date: date
    venue_or_project: str | None = Field(default=None, max_length=240)
    venue_address: str | None = Field(default=None, max_length=2000)
    package_name: str | None = Field(default=None, max_length=160)
    quoted_total: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    balance_due_date: date | None = None
    notes: str | None = Field(default=None, max_length=10000)
    client: LegacyClientIn
    quote: LegacyQuoteIn
    invoice: LegacyInvoiceIn
    booking_form: LegacyFormIn
    final_questionnaire: LegacyFormIn | None = None
    contract: LegacyContractIn | None = None
    legacy_timeline: list[dict] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def financial_totals_match(self):
        if self.quote.total != self.invoice.total:
            raise ValueError("The accepted quote total must match the imported invoice total")
        if self.quoted_total and self.quoted_total != self.invoice.total:
            raise ValueError("The booking total must match the imported invoice total")
        return self


class LegacyImportRequest(BaseModel):
    confirmation: str
    record: LegacyRecordIn


def _validate_confirmation(value: str) -> None:
    if value.strip() != "IMPORT WITHOUT EMAILS":
        raise HTTPException(422, "Type IMPORT WITHOUT EMAILS exactly to confirm")


def _existing_legacy_booking(db: Session, legacy_id: str) -> Booking | None:
    return db.scalar(select(Booking).where(
        Booking.legacy_source == "studio_ninja",
        Booking.legacy_id == legacy_id,
    ))


def _complete_imported_tasks(
    db: Session, booking: Booking, has_payment: bool, has_contract_acceptance: bool
) -> None:
    for task in db.scalars(select(Task).where(Task.booking_id == booking.id)).all():
        title = task.title.lower()
        if ("quote" in title or "booking form" in title
                or (has_contract_acceptance and "contract" in title)
                or (has_payment and "deposit" in title)):
            task.completed = True


def register_legacy_import_routes(app: FastAPI) -> None:
    @app.get("/api/legacy-import/readiness")
    def legacy_import_readiness(
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        counters = db.scalars(select(InvoiceCounter)).all()
        return {
            "mode": "protected_no_email",
            "confirmation": "IMPORT WITHOUT EMAILS",
            "imported_records": db.scalar(select(func.count()).select_from(Booking).where(
                Booking.legacy_source == "studio_ninja"
            )) or 0,
            "automation_suppressed": db.scalar(select(func.count()).select_from(Booking).where(
                Booking.automation_suppressed.is_(True)
            )) or 0,
            "invoice_counters": {row.key: row.value for row in counters},
        }

    @app.post("/api/legacy-import/validate")
    def validate_legacy_record(
        payload: LegacyImportRequest,
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        _validate_confirmation(payload.confirmation)
        existing = _existing_legacy_booking(db, payload.record.legacy_id)
        return {
            "valid": existing is None,
            "duplicate": bool(existing),
            "existing_booking_id": existing.id if existing else None,
            "emails_will_be_sent": False,
            "reminders_will_run": False,
            "payment_count": len(payload.record.invoice.payments),
            "document_uploads_required": True,
        }

    @app.post("/api/legacy-import/records", status_code=201)
    def import_legacy_record(
        payload: LegacyImportRequest,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        _validate_confirmation(payload.confirmation)
        source = payload.record
        existing = _existing_legacy_booking(db, source.legacy_id)
        if existing:
            raise HTTPException(409, f"This Studio Ninja record is already linked to {existing.id}")

        try:
            client = Client(
                first_name=source.client.first_name.strip(),
                last_name=source.client.last_name.strip(),
                partner_name=source.client.partner_name,
                email=str(source.client.email).lower(),
                phone=source.client.phone,
                address=source.client.address,
            )
            db.add(client)
            db.flush()

            paid_total = sum((row.amount for row in source.invoice.payments), Decimal("0"))
            first_paid = min((row.paid_date for row in source.invoice.payments), default=None)
            workflow_state = {
                "source": "studio_ninja_legacy_import",
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "imported_by": admin.email,
                "legacy_timeline": source.legacy_timeline,
                "final_details_manual_unlock": False,
            }
            booking = Booking(
                brand=Brand.WBM,
                kind=RecordKind.WEDDING,
                status=source.status,
                title=source.title,
                client_id=client.id,
                event_date=source.event_date,
                venue_or_project=source.venue_or_project,
                venue_address=source.venue_address,
                package_name=source.package_name,
                quoted_total=source.invoice.total,
                deposit_amount=source.deposit_amount,
                deposit_paid_date=first_paid,
                balance_due_date=source.balance_due_date or source.invoice.due_date,
                notes=source.notes,
                form_data=source.booking_form.data,
                workflow_state=workflow_state,
                legacy_source="studio_ninja",
                legacy_id=source.legacy_id,
                legacy_import_batch=source.import_batch,
                automation_suppressed=True,
            )
            db.add(booking)
            db.flush()

            sequence, number = next_invoice_number(db, Brand.WBM)
            invoice = Invoice(
                booking_id=booking.id,
                brand=Brand.WBM,
                sequence=sequence,
                number=number,
                issue_date=source.invoice.issue_date,
                deposit_due_date=source.invoice.deposit_due_date,
                supply_date=source.invoice.supply_date or source.event_date,
                due_date=source.invoice.due_date,
                description=source.invoice.description,
                total=source.invoice.total,
                paid=paid_total,
                status=invoice_status(source.invoice.total, paid_total),
                notes=source.invoice.notes,
                line_items=source.invoice.line_items,
                payment_schedule=[row.model_dump(mode="json") for row in source.invoice.payment_schedule],
                legacy_number=source.invoice.legacy_number,
                legacy_quote_number=source.invoice.legacy_quote_number,
                legacy_source="studio_ninja",
            )
            db.add(invoice)
            db.flush()
            for row in source.invoice.payments:
                db.add(Payment(
                    invoice_id=invoice.id,
                    amount=row.amount,
                    paid_date=row.paid_date,
                    payment_type=row.payment_type,
                    reference=row.reference,
                    notes=row.notes,
                    legacy_source="studio_ninja",
                    legacy_reference=row.legacy_reference,
                ))

            quote = Quote(
                booking_id=booking.id,
                status="accepted",
                line_items=source.quote.line_items,
                total=source.quote.total,
                deposit_amount=source.quote.deposit_amount,
                invoice_id=invoice.id,
                accepted_at=source.quote.accepted_at,
                legacy_number=source.quote.legacy_number,
                legacy_source="studio_ninja",
            )
            db.add(quote)

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
            has_contract_acceptance = bool(contract and contract.date_source != "manual_review")
            if has_contract_acceptance and contract:
                db.add(ContractAcceptance(
                    booking_id=booking.id,
                    contract_title=contract.contract_title,
                    contract_version=contract.contract_version,
                    contract_body=contract.contract_body,
                    accepted_name=contract.accepted_name,
                    accepted_email=str(contract.accepted_email).lower(),
                    ip_address=None,
                    user_agent=None,
                    accepted_at=contract.accepted_at,
                    acceptance_source=contract.date_source,
                    source_detail=(contract.source_detail
                                   or "Imported from Studio Ninja; original contract PDF retained"),
                    is_legacy_import=True,
                ))
            else:
                workflow_state["contract_review_required"] = True
                booking.workflow_state = workflow_state
            _complete_imported_tasks(db, booking, paid_total > 0, has_contract_acceptance)
            audit(db, "legacy_import_record", "booking", booking.id, {
                "source": "studio_ninja",
                "legacy_id": source.legacy_id,
                "batch": source.import_batch,
                "new_invoice": number,
                "legacy_invoice": source.invoice.legacy_number,
                "payments": len(source.invoice.payments),
                "contract_date_source": contract.date_source if contract else "manual_review",
                "emails_sent": False,
                "automation_suppressed": True,
            })
            db.commit()
        except Exception:
            db.rollback()
            raise

        return {
            "ok": True,
            "booking_id": booking.id,
            "invoice_id": invoice.id,
            "invoice_number": number,
            "legacy_invoice_number": source.invoice.legacy_number,
            "emails_sent": False,
            "automation_suppressed": True,
            "message": "Imported safely with all client automation paused",
        }

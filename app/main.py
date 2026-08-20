import asyncio
import hashlib
import mimetypes
import re
import secrets
import shutil
import uuid
from contextlib import suppress
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.background import BackgroundTask
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .bootstrap import bootstrap
from .backup import BACKUP_BUILD, BackupBusyError, create_complete_backup
from .booking_forms import public_booking_form, validate_booking_answers, validate_booking_form
from .accounts_integration import accounts_sync_loop, register_accounts_integration_routes
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .email_service import preview_template_email, send_template_email, smtp_credentials, smtp_ready
from .enquiry_forms import public_enquiry_form, validate_enquiry_answers, validate_enquiry_form
from .google_calendar import (google_calendar_configured, register_google_calendar_routes,
                              sync_booking_calendar_safely)
from .final_timings import (FORM_TYPE as FINAL_TIMINGS_FORM_TYPE,
                            booking_coverage_allowance, final_timings_unlocked,
                            studio_ninja_final_timings_email_due,
                            validated_final_timings)
from .migrations import apply_safe_migrations
from .legacy_archive_import import register_legacy_archive_import_routes
from .legacy_import import register_legacy_import_routes
from .mail_routes import register_mail_routes
from .models import (AddOnOption, Admin, AuditLog, Booking, BookingNote, Brand, BusinessProfile,
                     Client, ClientPortalToken, ContractAcceptance, ContractTemplate, Document,
                     EmailLog, EmailTemplate, FormSubmission, FormTemplate, Invoice, PackageOption, Payment,
                     Quote, RecordKind, RecordStatus, ReminderLog, SystemSetting, Task)
from .pdf import contract_acceptance_pdf, final_timings_pdf, invoice_pdf
from .schemas import (AddOnOptionIn, AddOnOptionPatch, BookingIn, BookingPatch, BusinessPatch,
                      ContractAcceptIn, ContractTemplatePatch, EmailTemplateIn, EmailTemplatePatch, EnquiryIn,
                      BookingFormTemplateIn, EnquiryFormTemplateIn,
                      InvoiceDueDatePatch, InvoiceIn,
                      LoginIn, NoteIn, PackageOptionIn, PackageOptionPatch, PaymentIn, PortalCreateIn,
                      ClientEmailComposeIn, PublicFormIn, QuoteAcceptIn, QuotePreparationIn,
                      SendEmailIn, TaskIn, TaskPatch,
                      TemplateTestIn, TestingModeIn)
from .security import create_token, current_admin, verify_password
from .services import (audit, create_default_tasks, dashboard_counts, invoice_status,
                       next_invoice_number, payment_reference, sync_final_details_call_task,
                       visible_task_condition)
from .v82_routes import register_v82_routes
from .v84_routes import automations_allowed, final_details_unlocked, register_v84_routes

settings = get_settings()
STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_UPLOADS = {"application/pdf", "image/jpeg", "image/png",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
ENQUIRY_HITS: dict[str, list[datetime]] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    apply_safe_migrations()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        bootstrap(db)
    reminder_task = asyncio.create_task(reminder_loop())
    accounts_task = asyncio.create_task(accounts_sync_loop())
    yield
    reminder_task.cancel()
    accounts_task.cancel()
    with suppress(asyncio.CancelledError):
        await reminder_task
    with suppress(asyncio.CancelledError):
        await accounts_task


app = FastAPI(title=settings.app_name, version="2.8.22-client-updates-dashboard", lifespan=lifespan, docs_url=None, redoc_url=None)


def money(value) -> float:
    return float(value or 0)


def portal_lifetime_days(booking: Booking, minimum_days: int = 365) -> int:
    """Keep a wedding link valid through the event and for a year afterwards."""
    if booking.event_date:
        through_aftercare = (booking.event_date - date.today()).days + 365
        return min(3650, max(minimum_days, through_aftercare))
    return max(minimum_days, 1095)


def issue_client_email_url(db: Session, booking: Booking, template_key: str,
                           minimum_days: int = 365) -> str:
    """Issue a fresh correct account link for an individual client email."""
    raw, _ = issue_portal_token(db, booking.id,
                                portal_lifetime_days(booking, max(365, minimum_days)))
    tabs = {
        "quote": "quote",
        "quote_followup_1": "quote",
        "quote_followup_final": "quote",
        "quote_accepted": "invoices",
        "deposit_due_1": "invoices",
        "payment_received": "invoices",
        "contract_completed": "agreement",
        "balance_due_7": "invoices",
        "balance_due_1": "invoices",
        "balance_overdue_2": "invoices",
        "contract_reminder": "agreement",
        "check_in_30": "timings",
    }
    tab = tabs.get(template_key)
    base = f"{settings.app_url.rstrip('/')}/client/{raw}"
    return f"{base}?tab={tab}" if tab else base


def confirm_when_paid(booking: Booking) -> bool:
    """Confirm an enquiry or quote after a dated payment has been recorded."""
    if (booking.status in (RecordStatus.ENQUIRY, RecordStatus.QUOTED)
            and money(booking.deposit_amount) > 0 and booking.deposit_paid_date):
        booking.status = RecordStatus.CONFIRMED
        return True
    return False


def testing_mode(db: Session) -> dict:
    row = db.get(SystemSetting, "testing_mode")
    value = dict(row.value or {}) if row else {}
    return {"enabled": bool(value.get("enabled")),
            "email": str(value.get("email") or settings.admin_email).lower()}


def client_email_recipient(db: Session, booking: Booking) -> str:
    """A test record can never send to the address entered as the client."""
    if booking.is_test:
        saved = (booking.workflow_state or {}).get("test_email")
        return str(saved or testing_mode(db)["email"]).lower()
    return booking.client.email


def send_booking_template_email(db: Session, booking: Booking, profile: BusinessProfile,
                                template: EmailTemplate, portal_url: str | None = None,
                                **kwargs):
    """Keep the ordinary call signature unchanged; add a recipient override only for TEST records."""
    if booking.is_test:
        kwargs["recipient"] = client_email_recipient(db, booking)
    return send_template_email(booking, profile, template, portal_url, **kwargs)


def payment_plan_code(booking: Booking) -> str:
    code = str((booking.form_data or {}).get("payment_plan") or "standard")
    return code if code in {"standard", "split", "quarter"} else "standard"


def schedule_rows(total: Decimal, package_fee: Decimal, plan: str, accepted_on: date,
                  event_date: date | None) -> tuple[Decimal, date | None, list[dict]]:
    penny = Decimal("0.01")
    total = Decimal(total or 0).quantize(penny, rounding=ROUND_HALF_UP)
    package_fee = min(total, Decimal(package_fee or 0)).quantize(penny, rounding=ROUND_HALF_UP)
    deposit_due = accepted_on + timedelta(days=1)
    due_45 = max(event_date - timedelta(days=45), deposit_due) if event_date else None
    due_90 = max(event_date - timedelta(days=90), deposit_due) if event_date else None
    if plan == "quarter":
        first = (total * Decimal("0.25")).quantize(penny, rounding=ROUND_HALF_UP)
        rows = [
            {"key": "booking_25", "label": "25% booking payment", "amount": money(first),
             "due_date": deposit_due.isoformat(), "status": "scheduled"},
            {"key": "final_75", "label": "Remaining 75% balance", "amount": money(total - first),
             "due_date": due_45.isoformat() if due_45 else None, "status": "scheduled"},
        ]
        return first, due_45, rows
    remaining = max(Decimal("0"), total - package_fee)
    if plan == "split":
        first_half = (remaining / Decimal("2")).quantize(penny, rounding=ROUND_HALF_UP)
        second_half = remaining - first_half
        rows = [
            {"key": "booking_fee", "label": "Booking fee", "amount": money(package_fee),
             "due_date": deposit_due.isoformat(), "status": "scheduled"},
            {"key": "instalment_90", "label": "First balance instalment", "amount": money(first_half),
             "due_date": due_90.isoformat() if due_90 else None, "status": "scheduled"},
            {"key": "final_45", "label": "Final balance instalment", "amount": money(second_half),
             "due_date": due_45.isoformat() if due_45 else None, "status": "scheduled"},
        ]
        return package_fee, due_45, rows
    rows = [
        {"key": "booking_fee", "label": "Booking fee", "amount": money(package_fee),
         "due_date": deposit_due.isoformat(), "status": "scheduled"},
        {"key": "final_45", "label": "Remaining balance", "amount": money(remaining),
         "due_date": due_45.isoformat() if due_45 else None, "status": "scheduled"},
    ]
    return package_fee, due_45, rows


def allocated_schedule(invoice: Invoice) -> list[dict]:
    paid_left = Decimal(invoice.paid or 0)
    result = []
    for original in invoice.payment_schedule or []:
        item = dict(original)
        amount = Decimal(str(item.get("amount") or 0))
        applied = min(amount, max(Decimal("0"), paid_left))
        paid_left -= applied
        item["paid"] = money(applied)
        item["balance"] = money(max(Decimal("0"), amount - applied))
        item["status"] = "paid" if applied >= amount else "part_paid" if applied > 0 else "scheduled"
        result.append(item)
    return result


def apply_payment_plan(db: Session, booking: Booking, plan: str) -> None:
    """Rebuild only native invoices; original Studio Ninja schedules remain untouched."""
    if booking.legacy_source or booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING:
        return
    quote = db.scalar(select(Quote).where(Quote.booking_id == booking.id, Quote.status == "accepted")
                      .order_by(Quote.accepted_at.desc()).limit(1))
    if not quote or not quote.invoice_id:
        return
    invoice = db.get(Invoice, quote.invoice_id)
    if not invoice or invoice.legacy_source or invoice.status in ("void", "cancelled"):
        return
    package = db.get(PackageOption, quote.package_id) if quote.package_id else None
    accepted_on = quote.accepted_at.date() if quote.accepted_at else invoice.issue_date
    fee, final_due, rows = schedule_rows(Decimal(invoice.total),
                                         Decimal(package.deposit_amount if package else booking.deposit_amount),
                                         plan, accepted_on, booking.event_date)
    booking.deposit_amount = fee
    booking.balance_due_date = final_due
    quote.deposit_amount = fee
    invoice.deposit_due_date = accepted_on + timedelta(days=1)
    invoice.supply_date = booking.event_date
    invoice.due_date = final_due
    invoice.payment_schedule = rows
    invoice.notes = (f"Payment plan: {plan}. First payment of £{money(fee):,.2f} is due by "
                     f"{invoice.deposit_due_date.strftime('%d %B %Y')}. " +
                     (f"The final payment is due by {final_due.strftime('%d %B %Y')}."
                      if final_due else "Payment dates will be completed when the wedding date is set."))


def refresh_wedding_payment_dates(db: Session, booking: Booking) -> None:
    """Keep the accepted quote invoice aligned if the wedding date changes."""
    if booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING or not booking.event_date:
        return
    quote = db.scalar(select(Quote).where(Quote.booking_id == booking.id,
                                          Quote.status == "accepted")
                      .order_by(Quote.accepted_at.desc()).limit(1))
    if not quote:
        return
    apply_payment_plan(db, booking, payment_plan_code(booking))


def client_json(client: Client) -> dict:
    return {"id": client.id, "first_name": client.first_name, "last_name": client.last_name,
            "partner_name": client.partner_name, "company_name": client.company_name,
            "email": client.email, "phone": client.phone, "address": client.address}


def task_json(item: Task) -> dict:
    return {"id": item.id, "booking_id": item.booking_id, "booking_title": item.booking.title if item.booking else None,
            "title": item.title, "due_at": item.due_at.isoformat() if item.due_at else None,
            "completed": item.completed, "workflow_key": item.workflow_key,
            "created_at": item.created_at.isoformat()}


def payment_json(item: Payment) -> dict:
    return {"id": item.id, "amount": money(item.amount), "paid_date": item.paid_date.isoformat(),
            "payment_type": item.payment_type, "reference": item.reference, "notes": item.notes,
            "legacy_source": item.legacy_source, "legacy_reference": item.legacy_reference,
            "created_at": item.created_at.isoformat()}


def standard_wedding_due_date(item: Invoice) -> date | None:
    """Return the normal wedding payment date before any agreed exception."""
    booking = item.booking
    if (booking and booking.brand == Brand.WBM and booking.kind == RecordKind.WEDDING
            and booking.event_date):
        return booking.event_date - timedelta(days=45)
    return None


def effective_invoice_due_date(item: Invoice) -> date | None:
    """Return the next unpaid scheduled date, including an agreed final date."""
    scheduled = allocated_schedule(item)
    outstanding_dates = []
    for row in scheduled:
        raw = row.get("due_date")
        if row.get("balance", 0) > 0 and raw:
            try:
                outstanding_dates.append(date.fromisoformat(str(raw)))
            except ValueError:
                pass
    if outstanding_dates:
        return min(outstanding_dates)
    if item.due_date:
        return item.due_date
    if item.booking and item.booking.balance_due_date:
        return item.booking.balance_due_date
    return standard_wedding_due_date(item)


def invoice_void_record(item: Invoice) -> dict | None:
    """Recover the permanent void audit marker stored on current invoices.

    V8.2 deliberately stored this in the existing invoice notes field so no
    database migration was required. Exposing the structured parts here makes
    the reason visible without changing or rewriting the retained record.
    """
    if item.status != "void" or not item.notes:
        return None
    marker = re.search(
        r"VOIDED (?P<at>.+?) by (?P<by>.+?)\. Reason: (?P<reason>.*?)(?=\n\nVOIDED |\Z)",
        item.notes,
        flags=re.DOTALL,
    )
    if not marker:
        return {"reason": item.notes.strip(), "voided_at": None, "voided_by": None}
    return {
        "reason": marker.group("reason").strip(),
        "voided_at": marker.group("at").strip(),
        "voided_by": marker.group("by").strip(),
    }


def invoice_cancellation_record(item: Invoice) -> dict | None:
    """Return the latest permanent cancellation adjustment stored with an invoice."""
    if not item.notes:
        return None
    matches = list(re.finditer(
        r"CANCELLED (?P<at>\S+) by (?P<by>.+?)\. "
        r"Cancellation date: (?P<date>\d{4}-\d{2}-\d{2})\. "
        r"Unpaid balance closed: £(?P<closed>[0-9,.]+)\. "
        r"Reason: (?P<reason>.*?)(?=\n\n(?:CANCELLED|VOIDED) |\Z)",
        item.notes,
        flags=re.DOTALL,
    ))
    if not matches:
        return None
    marker = matches[-1]
    return {
        "reason": marker.group("reason").strip(),
        "cancelled_at": marker.group("at").strip(),
        "cancelled_by": marker.group("by").strip(),
        "cancellation_date": marker.group("date"),
        "closed_balance": float(marker.group("closed").replace(",", "")),
    }


def invoice_json(item: Invoice) -> dict:
    due = effective_invoice_due_date(item)
    standard_due = standard_wedding_due_date(item)
    closed = item.status in ("void", "cancelled")
    balance = Decimal("0") if closed else item.total - item.paid
    refunded = sum(
        -Decimal(payment.amount)
        for payment in item.payments
        if payment.payment_type == "refund" and Decimal(payment.amount) < 0
    )
    gross_paid = Decimal(item.paid or 0) + refunded
    days_until_due = (due - date.today()).days if due and balance > 0 else None
    due_status = ("paid" if balance <= 0 else "no_date" if not due else
                  "overdue" if days_until_due < 0 else "due_today" if days_until_due == 0 else "upcoming")
    schedule = allocated_schedule(item)
    return {"id": item.id, "booking_id": item.booking_id, "brand": item.brand.value,
            "sequence": item.sequence, "number": item.number, "issue_date": item.issue_date.isoformat(),
            "deposit_due_date": item.deposit_due_date.isoformat() if item.deposit_due_date else None,
            "supply_date": item.supply_date.isoformat() if item.supply_date else None,
            "due_date": item.due_date.isoformat() if item.due_date else (due.isoformat() if due else None),
            "payment_due_date": due.isoformat() if due else None,
            "standard_due_date": standard_due.isoformat() if standard_due else None,
            "due_date_overridden": bool(item.due_date and standard_due and item.due_date != standard_due),
            "final_due_date": item.due_date.isoformat() if item.due_date else None,
            "wedding_date": item.booking.event_date.isoformat() if item.booking and item.booking.event_date else None,
            "payment_due_status": due_status, "days_until_due": days_until_due,
            "description": item.description, "notes": item.notes,
            "void_record": invoice_void_record(item),
            "cancellation_record": invoice_cancellation_record(item),
            "total": money(item.total),
            "deposit_amount": money(item.booking.deposit_amount if item.booking else 0),
            "line_items": item.line_items or [],
            "payment_schedule": schedule,
            "legacy_number": item.legacy_number,
            "legacy_quote_number": item.legacy_quote_number,
            "legacy_source": item.legacy_source,
            "paid": money(item.paid),
            "gross_paid": money(gross_paid),
            "refunded": money(refunded),
            "balance": money(balance),
            "status": item.status,
            "payment_reference": payment_reference(item.booking, item.number) if item.booking else item.number,
            "client": item.booking.title if item.booking else None,
            "is_test": bool(item.booking and item.booking.is_test),
            "payments": [payment_json(p) for p in sorted(item.payments, key=lambda x: x.paid_date, reverse=True)]}


def package_json(item: PackageOption) -> dict:
    return {"id": item.id, "brand": item.brand.value, "code": item.code, "name": item.name,
            "description": item.description, "price": money(item.price),
            "deposit_amount": money(item.deposit_amount), "display_order": item.display_order,
            "is_active": item.is_active}


def addon_json(item: AddOnOption) -> dict:
    return {"id": item.id, "brand": item.brand.value, "code": item.code, "name": item.name,
            "description": item.description, "price": money(item.price),
            "eligible_package_codes": item.eligible_package_codes or [],
            "display_order": item.display_order, "is_active": item.is_active,
            "is_discount": item.is_discount}


def quote_json(item: Quote | None) -> dict | None:
    if not item:
        return None
    return {"id": item.id, "status": item.status, "package_id": item.package_id,
            "selected_addon_ids": item.selected_addon_ids or [], "line_items": item.line_items or [],
            "total": money(item.total), "deposit_amount": money(item.deposit_amount),
            "invoice_id": item.invoice_id,
            "legacy_number": item.legacy_number, "legacy_source": item.legacy_source,
            "accepted_at": item.accepted_at.isoformat() if item.accepted_at else None}


def document_json(item: Document) -> dict:
    return {"id": item.id, "booking_id": item.booking_id,
            "booking_title": item.booking.title if item.booking else None, "brand": item.booking.brand.value if item.booking else None,
            "category": item.category, "original_name": item.original_name, "content_type": item.content_type,
            "size_bytes": item.size_bytes, "source_system": item.source_system,
            "legacy_document_type": item.legacy_document_type,
            "legacy_reference": item.legacy_reference,
            "document_date": item.document_date.isoformat() if item.document_date else None,
            "is_client_visible": item.is_client_visible,
            "created_at": item.created_at.isoformat()}


def ensure_final_timings_document(db: Session, booking: Booking,
                                  submission: FormSubmission) -> tuple[Document, bytes]:
    """Create or refresh the private PDF retained in the booking's Files tab."""
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
    if not profile:
        raise HTTPException(503, "Business profile not found for the Final Wedding Timings PDF")
    content = final_timings_pdf(booking, submission, profile)
    document = db.get(Document, submission.source_document_id) if submission.source_document_id else None
    if not document or document.booking_id != booking.id:
        document = db.scalar(select(Document).where(
            Document.booking_id == booking.id,
            Document.source_system == "bookingsystem2026_generated",
            Document.legacy_reference == f"final_timings:{submission.id}",
        ).limit(1))
    safe_title = re.sub(r"[^A-Za-z0-9&'() ._-]", "_", booking.title or "Wedding")[:150].strip()
    original_name = f"Final Wedding Timings - {safe_title or 'Wedding'}.pdf"
    if not document:
        document = Document(
            booking_id=booking.id,
            category="final_timings",
            original_name=original_name,
            storage_name=f"{booking.id}/final_timings/{uuid.uuid4().hex}.pdf",
            content_type="application/pdf",
            size_bytes=len(content),
            source_system="bookingsystem2026_generated",
            legacy_reference=f"final_timings:{submission.id}",
            document_date=booking.event_date or date.today(),
            is_client_visible=False,
        )
        db.add(document)
        db.flush()
    target = settings.storage_root / document.storage_name
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".pdf.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    document.original_name = original_name
    document.content_type = "application/pdf"
    document.size_bytes = len(content)
    document.document_date = booking.event_date or date.today()
    submission.source_document_id = document.id
    db.flush()
    return document, content


def booking_json(item: Booking, full: bool = False, activity: list[AuditLog] | None = None) -> dict:
    data = {"id": item.id, "brand": item.brand.value, "kind": item.kind.value, "status": item.status.value,
            "title": item.title, "event_date": item.event_date.isoformat() if item.event_date else None,
            "venue_or_project": item.venue_or_project, "venue_address": item.venue_address,
            "venue_place_id": item.venue_place_id, "venue_lat": item.venue_lat, "venue_lng": item.venue_lng,
            "package_name": item.package_name,
            "quoted_total": money(item.quoted_total), "deposit_amount": money(item.deposit_amount),
            "payment_reference": payment_reference(item),
            "deposit_paid_date": item.deposit_paid_date.isoformat() if item.deposit_paid_date else None,
            "balance_due_date": item.balance_due_date.isoformat() if item.balance_due_date else None,
            "client": client_json(item.client), "archived": item.archived_at is not None,
            "legacy_source": item.legacy_source, "legacy_id": item.legacy_id,
            "legacy_import_batch": item.legacy_import_batch,
            "automation_suppressed": item.automation_suppressed,
            "is_test": item.is_test,
            "archived_at": item.archived_at.isoformat() if item.archived_at else None,
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}
    if full:
        visible_tasks = [
            task for task in item.tasks
            if not (
                item.legacy_source == "studio_ninja"
                and (task.workflow_key or "").startswith("step_")
            )
        ]
        data.update({"notes": item.notes, "form_data": item.form_data, "workflow_state": item.workflow_state,
                     "legacy_timeline": (item.workflow_state or {}).get("legacy_timeline", []),
                     "tasks": [task_json(t) for t in sorted(visible_tasks, key=lambda x: (x.completed, x.created_at))],
                     "invoices": [invoice_json(i) for i in sorted(item.invoices, key=lambda x: x.sequence, reverse=True)],
                     "documents": [document_json(d) for d in sorted(item.documents, key=lambda x: x.created_at, reverse=True)],
                     "booking_notes": [{"id": n.id, "body": n.body, "created_at": n.created_at.isoformat()}
                                       for n in sorted(item.booking_notes, key=lambda x: x.created_at, reverse=True)],
                     "activity": [{"id": a.id, "action": a.action, "entity_type": a.entity_type,
                                   "details": a.details, "created_at": a.created_at.isoformat()}
                                  for a in (activity or [])]})
    return data


def full_booking(db: Session, booking_id: str) -> Booking:
    item = db.scalar(select(Booking).options(
        selectinload(Booking.client), selectinload(Booking.tasks),
        selectinload(Booking.invoices).selectinload(Invoice.payments),
        selectinload(Booking.documents), selectinload(Booking.booking_notes),
        selectinload(Booking.quotes)
    ).where(Booking.id == booking_id))
    if not item:
        raise HTTPException(404, "Record not found")
    return item


@app.get("/api/health")
def health():
    return {"status": "ok", "phase": "2B", "smtp_configured": smtp_ready(),
            "reminders_enabled": settings.reminders_enabled,
            "maps_configured": bool(settings.google_maps_api_key),
            "imap_configured": bool(settings.imap_host and (
                settings.imap_wbm_password or settings.smtp_wbm_password or
                settings.imap_ivory_password or settings.smtp_ivory_password)),
            "accounts_integration_enabled": settings.accounts_integration_enabled,
            "accounts_auto_sync": settings.accounts_integration_auto_sync,
            "google_calendar_configured": google_calendar_configured(),
            "build": BACKUP_BUILD}


@app.get("/api/public/config")
def public_config():
    """Browser-safe public configuration. The Maps key must be website/API restricted in Google Cloud."""
    return {"google_maps_api_key": settings.google_maps_api_key,
            "google_maps_enabled": bool(settings.google_maps_api_key)}


@app.get("/api/public/catalog")
def public_catalog(db: Session = Depends(get_db)):
    packages = db.scalars(select(PackageOption).where(PackageOption.brand == Brand.WBM,
                                                       PackageOption.is_active.is_(True))
                          .order_by(PackageOption.display_order, PackageOption.price)).all()
    return {"packages": [package_json(x) for x in packages]}


def website_date_is_booked(db: Session, wedding_date: date) -> bool:
    """Return availability without exposing any client or wedding details.

    Native and imported Weddings By Mark jobs both protect the date. Enquiries,
    unaccepted quotes, cancelled bookings and Testing Mode records do not.
    Archived active jobs remain protected so hiding a record cannot accidentally
    advertise its date as available.
    """
    accepted_quote = select(Quote.id).where(
        Quote.booking_id == Booking.id,
        Quote.status == "accepted",
    ).exists()
    booking_id = db.scalar(select(Booking.id).where(
        Booking.brand == Brand.WBM,
        Booking.kind == RecordKind.WEDDING,
        Booking.event_date == wedding_date,
        Booking.is_test.is_(False),
        Booking.status != RecordStatus.CANCELLED,
        or_(
            Booking.status.in_([
                RecordStatus.CONFIRMED,
                RecordStatus.IN_PROGRESS,
                RecordStatus.COMPLETED,
            ]),
            accepted_quote,
        ),
    ).limit(1))
    return booking_id is not None


@app.get("/api/public/availability")
def public_wedding_availability(date: date = Query(...), db: Session = Depends(get_db)):
    """Privacy-safe live date result for the public website checker."""
    result = "Unavailable" if date < datetime.now().astimezone().date() else (
        "Booked" if website_date_is_booked(db, date) else "Available"
    )
    return Response(
        content=result,
        media_type="text/plain",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


def website_enquiry_template(db: Session) -> FormTemplate:
    item = db.scalar(select(FormTemplate).where(
        FormTemplate.brand == Brand.WBM,
        FormTemplate.template_key == "website_enquiry",
    ))
    if not item:
        raise HTTPException(503, "The website enquiry form is not configured yet")
    return item


@app.get("/api/public/enquiry-form")
def public_website_enquiry_form(db: Session = Depends(get_db)):
    item = website_enquiry_template(db)
    if not item.is_active:
        raise HTTPException(503, "The website enquiry form is temporarily unavailable")
    return public_enquiry_form(item.config or {})


@app.get("/api/forms/website-enquiry")
def admin_website_enquiry_form(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = website_enquiry_template(db)
    config = dict(item.config or {})
    config.update({"id": item.id, "display_name": item.display_name,
                   "is_active": item.is_active, "updated_at": item.updated_at.isoformat()})
    return config


@app.put("/api/forms/website-enquiry")
def save_website_enquiry_form(payload: EnquiryFormTemplateIn,
                              _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = website_enquiry_template(db)
    config = validate_enquiry_form(payload.model_dump())
    item.config = config
    item.is_active = True
    audit(db, "publish_website_enquiry_form", "form_template", item.id,
          {"question_count": len(config["fields"])})
    db.commit()
    db.refresh(item)
    result = dict(item.config)
    result.update({"id": item.id, "display_name": item.display_name,
                   "is_active": item.is_active, "updated_at": item.updated_at.isoformat()})
    return result


def wedding_booking_template(db: Session) -> FormTemplate:
    item = db.scalar(select(FormTemplate).where(
        FormTemplate.brand == Brand.WBM,
        FormTemplate.template_key == "wedding_booking_form",
    ))
    if not item:
        raise HTTPException(503, "The Wedding Booking Form is not configured yet")
    return item


@app.get("/api/forms/wedding-booking")
def admin_wedding_booking_form(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = wedding_booking_template(db)
    result = dict(item.config or {})
    result.update({"id": item.id, "display_name": item.display_name,
                   "is_active": item.is_active, "updated_at": item.updated_at.isoformat()})
    return result


@app.put("/api/forms/wedding-booking")
def save_wedding_booking_form(payload: BookingFormTemplateIn,
                              _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = wedding_booking_template(db)
    item.config = validate_booking_form(payload.model_dump())
    item.is_active = True
    audit(db, "publish_wedding_booking_form", "form_template", item.id,
          {"question_count": len(item.config["fields"])})
    db.commit()
    db.refresh(item)
    result = dict(item.config)
    result.update({"id": item.id, "display_name": item.display_name,
                   "is_active": item.is_active, "updated_at": item.updated_at.isoformat()})
    return result


@app.get("/api/testing-mode")
def get_testing_mode(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    mode = testing_mode(db)
    mode["record_count"] = len(db.scalars(select(Booking.id).where(Booking.is_test.is_(True))).all())
    return mode


@app.put("/api/testing-mode")
def save_testing_mode(payload: TestingModeIn, _: Admin = Depends(current_admin),
                      db: Session = Depends(get_db)):
    row = db.get(SystemSetting, "testing_mode")
    value = {"enabled": payload.enabled, "email": str(payload.email).lower()}
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key="testing_mode", value=value))
    audit(db, "change_testing_mode", "system_setting", "testing_mode", value)
    db.commit()
    return {**value, "record_count": len(db.scalars(select(Booking.id).where(Booking.is_test.is_(True))).all())}


@app.post("/api/public/enquiries", status_code=201)
def create_public_enquiry(payload: EnquiryIn, request: Request, db: Session = Depends(get_db)):
    if payload.website:
        return {"ok": True}
    if not payload.privacy_agreed:
        raise HTTPException(422, "Please agree to the privacy notice before submitting")
    template = website_enquiry_template(db)
    core_answers = payload.model_dump(exclude={"website", "privacy_agreed", "custom_answers"}, mode="json")
    custom_answers, answer_snapshot = validate_enquiry_answers(
        template.config or {},
        {**core_answers, "privacy_agreed": payload.privacy_agreed},
        payload.custom_answers,
    )
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    client_ip = forwarded or (request.client.host if request.client else "unknown")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = [stamp for stamp in ENQUIRY_HITS.get(client_ip, []) if stamp > cutoff]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many enquiries have been submitted. Please try again later.")
    recent.append(datetime.now(timezone.utc))
    ENQUIRY_HITS[client_ip] = recent

    client = Client(first_name=payload.primary_first_name.strip(), last_name="",
                    partner_name=payload.partner_first_name.strip(), email=str(payload.email).lower(),
                    phone=payload.phone.strip() if payload.phone else None)
    db.add(client)
    db.flush()
    form_data = {**core_answers, "custom_answers": custom_answers,
                 "answer_snapshot": answer_snapshot,
                 "form_template_updated_at": template.updated_at.isoformat()}
    title = f"{payload.primary_first_name.strip()} & {payload.partner_first_name.strip()}"
    test_mode = testing_mode(db)
    booking = Booking(brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.ENQUIRY,
                      title=title, client_id=client.id, event_date=payload.event_date,
                      venue_or_project=payload.location.strip(), venue_address=payload.venue_address,
                      venue_place_id=payload.venue_place_id, venue_lat=payload.venue_lat,
                      venue_lng=payload.venue_lng, package_name=payload.package_interest,
                      notes=payload.message.strip() if payload.message else None,
                      form_data={"website_enquiry": form_data}, is_test=test_mode["enabled"],
                      workflow_state={"source": "website_enquiry", "received_at": datetime.now(timezone.utc).isoformat(),
                                      **({"test_email": test_mode["email"]} if test_mode["enabled"] else {})})
    db.add(booking)
    db.flush()
    create_default_tasks(db, booking.id, booking.kind, booking.event_date)
    raw_portal_token, portal_row = issue_portal_token(
        db, booking.id, portal_lifetime_days(booking)
    )
    portal_url = f"{settings.app_url.rstrip('/')}/client/{raw_portal_token}"
    audit(db, "website_enquiry", "booking", booking.id,
          {"title": title, "event_date": payload.event_date.isoformat(),
           "heard_about_us": payload.heard_about_us,
           "portal_expires_at": portal_row.expires_at.isoformat()})

    acknowledgement = db.scalar(select(EmailTemplate).where(EmailTemplate.brand == Brand.WBM,
                                                            EmailTemplate.template_key == "enquiry_received",
                                                            EmailTemplate.is_active.is_(True)))
    admin_notification = db.scalar(select(EmailTemplate).where(
        EmailTemplate.brand == Brand.WBM,
        EmailTemplate.template_key == "new_enquiry_admin",
        EmailTemplate.is_active.is_(True)))
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == Brand.WBM))
    if profile and smtp_ready(Brand.WBM):
        if acknowledgement:
            try:
                recipient = client_email_recipient(db, booking)
                subject, email_body = send_booking_template_email(
                    db, booking, profile, acknowledgement, portal_url
                )
                db.add(EmailLog(booking_id=booking.id, template_key=acknowledgement.template_key,
                                recipient=recipient, subject=subject, body=email_body, status="sent"))
            except Exception as exc:
                db.add(EmailLog(booking_id=booking.id, template_key=acknowledgement.template_key,
                                recipient=client_email_recipient(db, booking), subject=acknowledgement.subject,
                                status="failed", error=str(exc)[:2000]))
        if admin_notification:
            notification_recipient = "mark@perfectweddingsbymark.uk"
            try:
                subject, email_body = send_template_email(
                    booking, profile, admin_notification,
                    extra_values={
                        "package_interest": payload.package_interest or "Not selected",
                        "selfie_booth_interest": payload.selfie_booth_interest or "Not answered",
                        "promo_code": payload.promo_code or "None entered",
                        "heard_about_us": payload.heard_about_us,
                        "enquiry_message": payload.message or "No additional message",
                        "fun_answer": payload.fun_answer or "Not answered",
                        "admin_url": settings.app_url.rstrip("/"),
                    },
                    recipient=notification_recipient,
                    reply_to=client_email_recipient(db, booking),
                )
                db.add(EmailLog(booking_id=booking.id, template_key=admin_notification.template_key,
                                recipient=notification_recipient, subject=subject,
                                body=email_body, status="sent"))
            except Exception as exc:
                db.add(EmailLog(booking_id=booking.id, template_key=admin_notification.template_key,
                                recipient=notification_recipient, subject=admin_notification.subject,
                                status="failed", error=str(exc)[:2000]))
    db.commit()
    return {"ok": True, "portal_created": True,
            "message": "Thank you - your enquiry has been received."}


@app.post("/api/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    admin = db.scalar(select(Admin).where(Admin.email == payload.email.lower()))
    if not admin or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect")
    response.set_cookie("booking_session", create_token(admin), httponly=True, secure=settings.cookie_secure,
                        samesite="strict", max_age=settings.session_hours * 3600, path="/")
    audit(db, "login", "admin", admin.id)
    db.commit()
    return {"ok": True, "name": "Mark Powell", "email": admin.email}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("booking_session", path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(admin: Admin = Depends(current_admin)):
    return {"id": admin.id, "email": admin.email, "name": "Mark Powell"}


@app.get("/api/businesses")
def businesses(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(BusinessProfile).order_by(BusinessProfile.display_name)).all()
    return [{"brand": r.brand.value, "display_name": r.display_name, "legal_name": r.legal_name,
             "invoice_prefix": r.invoice_prefix, "email": r.email, "phone": r.phone,
             "website": r.website, "address": r.address, "bank_details": r.bank_details or {}} for r in rows]


@app.get("/api/backups/complete")
def download_complete_backup(admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    """Download a private, portable snapshot without changing business workflows."""
    try:
        path, filename, manifest = create_complete_backup(db)
    except BackupBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit(db, "download_complete_backup", "admin", admin.id, {
        "filename": filename,
        "database_row_count": manifest["database_row_count"],
        "uploaded_file_count": manifest["uploaded_file_count"],
        "generated_pdf_count": manifest["generated_pdf_count"],
    })
    db.commit()
    return FileResponse(
        path,
        media_type="application/zip",
        filename=filename,
        headers={"Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff"},
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@app.patch("/api/businesses/{brand}")
def patch_business(brand: Brand, payload: BusinessPatch, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == brand))
    if not profile:
        raise HTTPException(404, "Business profile not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    audit(db, "update", "business", profile.id, {"brand": brand.value, "fields": list(payload.model_fields_set)})
    db.commit()
    return businesses(_, db)


@app.get("/api/catalog")
def catalog(brand: Brand = Brand.WBM, include_inactive: bool = False,
            _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    package_stmt = select(PackageOption).where(PackageOption.brand == brand)
    addon_stmt = select(AddOnOption).where(AddOnOption.brand == brand)
    if not include_inactive:
        package_stmt = package_stmt.where(PackageOption.is_active.is_(True))
        addon_stmt = addon_stmt.where(AddOnOption.is_active.is_(True))
    packages = db.scalars(package_stmt.order_by(PackageOption.display_order, PackageOption.price)).all()
    addons = db.scalars(addon_stmt.order_by(AddOnOption.display_order, AddOnOption.price)).all()
    return {"packages": [package_json(x) for x in packages], "addons": [addon_json(x) for x in addons]}


@app.post("/api/catalog/packages", status_code=201)
def create_package(payload: PackageOptionIn, brand: Brand = Brand.WBM,
                   _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if db.scalar(select(PackageOption).where(PackageOption.brand == brand,
                                             PackageOption.code == payload.code)):
        raise HTTPException(409, "That package code already exists")
    row = PackageOption(brand=brand, **payload.model_dump())
    db.add(row)
    db.flush()
    audit(db, "create_package", "package_option", row.id, {"name": row.name})
    db.commit()
    return package_json(row)


@app.patch("/api/catalog/packages/{package_id}")
def patch_package(package_id: str, payload: PackageOptionPatch,
                  _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    row = db.get(PackageOption, package_id)
    if not row:
        raise HTTPException(404, "Package not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    audit(db, "update_package", "package_option", row.id, {"name": row.name})
    db.commit()
    return package_json(row)


def catalog_item_is_used(db: Session, item_type: str, item_id: str, code: str) -> bool:
    """Protect accepted quote and invoice snapshots from catalog deletion."""
    for quote in db.scalars(select(Quote)).all():
        if item_type == "package" and quote.package_id == item_id:
            return True
        if item_type == "addon" and item_id in (quote.selected_addon_ids or []):
            return True
        if any(line.get("type") == item_type and line.get("code") == code
               for line in (quote.line_items or []) if isinstance(line, dict)):
            return True
    for invoice in db.scalars(select(Invoice)).all():
        if any(line.get("type") == item_type and line.get("code") == code
               for line in (invoice.line_items or []) if isinstance(line, dict)):
            return True
    return False


@app.delete("/api/catalog/packages/{package_id}", status_code=204)
def delete_package(package_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    row = db.get(PackageOption, package_id)
    if not row:
        raise HTTPException(404, "Package not found")
    if catalog_item_is_used(db, "package", row.id, row.code):
        raise HTTPException(409, "This package is already used by an accepted quote or invoice. Set it to Hidden instead so the client's records remain accurate.")
    for addon in db.scalars(select(AddOnOption).where(AddOnOption.brand == row.brand)).all():
        eligible = list(addon.eligible_package_codes or [])
        if row.code in eligible:
            addon.eligible_package_codes = [code for code in eligible if code != row.code]
    audit(db, "delete_package", "package_option", row.id, {"name": row.name, "code": row.code})
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@app.post("/api/catalog/addons", status_code=201)
def create_addon(payload: AddOnOptionIn, brand: Brand = Brand.WBM,
                 _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if db.scalar(select(AddOnOption).where(AddOnOption.brand == brand, AddOnOption.code == payload.code)):
        raise HTTPException(409, "That add-on code already exists")
    row = AddOnOption(brand=brand, **payload.model_dump())
    db.add(row)
    db.flush()
    audit(db, "create_addon", "addon_option", row.id, {"name": row.name})
    db.commit()
    return addon_json(row)


@app.patch("/api/catalog/addons/{addon_id}")
def patch_addon(addon_id: str, payload: AddOnOptionPatch,
                _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    row = db.get(AddOnOption, addon_id)
    if not row:
        raise HTTPException(404, "Add-on not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    audit(db, "update_addon", "addon_option", row.id, {"name": row.name})
    db.commit()
    return addon_json(row)


@app.delete("/api/catalog/addons/{addon_id}", status_code=204)
def delete_addon(addon_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    row = db.get(AddOnOption, addon_id)
    if not row:
        raise HTTPException(404, "Add-on not found")
    if catalog_item_is_used(db, "addon", row.id, row.code):
        raise HTTPException(409, "This add-on is already used by an accepted quote or invoice. Set it to Hidden instead so the client's records remain accurate.")
    audit(db, "delete_addon", "addon_option", row.id, {"name": row.name, "code": row.code})
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@app.get("/api/dashboard")
def dashboard(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    counts = dashboard_counts(db)
    upcoming = db.scalars(select(Booking).options(selectinload(Booking.client))
                          .where(Booking.archived_at.is_(None),
                                 Booking.status != RecordStatus.CANCELLED,
                                 Booking.event_date >= date.today())
                          .order_by(Booking.event_date).limit(8)).all()
    tasks = db.scalars(select(Task).options(selectinload(Task.booking))
                       .join(Booking).where(Task.completed.is_(False),
                                            Booking.archived_at.is_(None),
                                            Booking.status != RecordStatus.CANCELLED,
                                            visible_task_condition())
                       .order_by(Task.due_at.asc().nullslast()).limit(10)).all()
    counts.update({"upcoming": [booking_json(x) for x in upcoming], "tasks": [task_json(t) for t in tasks]})
    return counts


@app.get("/api/workflow-queues")
def workflow_queues(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    """Return the practical, read-only queues used by the V8.11 Today screen.

    The endpoint deliberately performs no workflow mutations. Imported Studio
    Ninja bookings remain excluded from the new-system quote/form/agreement
    chase queues, while their genuine payment and private phone tasks stay
    visible to Mark.
    """
    bookings = list(db.scalars(
        select(Booking).options(
            selectinload(Booking.client),
            selectinload(Booking.quotes),
            selectinload(Booking.tasks),
            selectinload(Booking.invoices).selectinload(Invoice.payments),
        ).where(
            Booking.archived_at.is_(None),
            Booking.status != RecordStatus.CANCELLED,
        ).order_by(Booking.created_at.desc())
    ).unique().all())
    booking_ids = [booking.id for booking in bookings]
    submission_rows = list(db.scalars(select(FormSubmission).where(
        FormSubmission.booking_id.in_(booking_ids),
        FormSubmission.form_type.in_(("booking_form", FINAL_TIMINGS_FORM_TYPE)),
    )).all()) if booking_ids else []
    booking_form_submissions = {
        row.booking_id: row for row in submission_rows if row.form_type == "booking_form"
    }
    final_timings_submissions = {
        row.booking_id: row for row in submission_rows
        if row.form_type == FINAL_TIMINGS_FORM_TYPE
    }
    submissions = set(booking_form_submissions)
    contracts = {
        row.booking_id: row for row in db.scalars(select(ContractAcceptance).where(
            ContractAcceptance.booking_id.in_(booking_ids)
        )).all()
    } if booking_ids else {}

    queues: dict[str, list[dict]] = {
        "client_updates": [],
        "new_enquiries": [],
        "quotes_waiting": [],
        "accepted_payment": [],
        "forms_waiting": [],
        "agreements_waiting": [],
        "payments_due": [],
        "overdue_payments": [],
        "final_calls": [],
    }
    today = date.today()
    # Payment planning is useful further ahead than the short operational task
    # window. Keep final-detail calls at 14 days while showing Mark every open
    # payment due during the next 60 days.
    payments_due_through = today + timedelta(days=60)
    final_calls_due_through = today + timedelta(days=14)

    def item(booking: Booking, detail: str, section: str, action: str,
             *, due: date | None = None, amount: Decimal | float | None = None,
             occurred_at: datetime | None = None, update_type: str | None = None) -> dict:
        return {
            "booking_id": booking.id,
            "title": booking.title,
            "detail": detail,
            "section": section,
            "action": action,
            "brand": booking.brand.value,
            "event_date": booking.event_date.isoformat() if booking.event_date else None,
            "due_date": due.isoformat() if due else None,
            "amount": money(amount) if amount is not None else None,
            "occurred_at": occurred_at.isoformat() if occurred_at else None,
            "update_type": update_type,
        }

    for booking in bookings:
        accepted_quote = next((quote for quote in booking.quotes if quote.status == "accepted"), None)
        paid = sum(Decimal(invoice.paid or 0) for invoice in booking.invoices)
        has_payment = paid > 0 or booking.deposit_paid_date is not None
        booking_form_complete = booking.id in submissions
        contract = contracts.get(booking.id)
        agreement_complete = bool(contract and (
            contract.is_legacy_import or contract.supplier_signed_at
        ))
        native_workflow = booking.legacy_source != "studio_ninja" and booking.kind == RecordKind.WEDDING
        open_task_keys = {
            task.workflow_key for task in booking.tasks if not task.completed and task.workflow_key
        }

        booking_form_submission = booking_form_submissions.get(booking.id)
        if (booking_form_submission
                and "wbm_review_booking_form" in open_task_keys):
            queues["client_updates"].append(item(
                booking,
                f"Wedding Booking Form submitted · {booking_form_submission.submission_source.replace('_', ' ')}",
                "Journey", "review_booking_form",
                occurred_at=booking_form_submission.updated_at,
                update_type="booking_form",
            ))
        final_submission = final_timings_submissions.get(booking.id)
        if final_submission and "wbm_review_final_timings" in open_task_keys:
            queues["client_updates"].append(item(
                booking,
                "Final Wedding Timings submitted and ready for your review",
                "Journey", "review_final_timings",
                occurred_at=final_submission.updated_at,
                update_type="final_timings",
            ))
        if (contract and not contract.is_legacy_import and not contract.supplier_signed_at):
            queues["client_updates"].append(item(
                booking,
                f"Agreement signed by {contract.accepted_name} · your countersignature is needed",
                "Journey", "countersign",
                occurred_at=contract.accepted_at,
                update_type="agreement",
            ))

        if native_workflow and booking.status == RecordStatus.ENQUIRY and not accepted_quote:
            queues["new_enquiries"].append(item(
                booking, booking.venue_or_project or booking.client.email,
                "Journey", "send_quote",
            ))
        elif native_workflow and booking.status == RecordStatus.QUOTED and not accepted_quote:
            queues["quotes_waiting"].append(item(
                booking, "Quote sent · waiting for the couple's package choice",
                "Journey", "view_quote",
            ))
        elif native_workflow and accepted_quote and not has_payment:
            queues["accepted_payment"].append(item(
                booking, f"{booking.package_name or 'Package'} accepted · first payment not recorded",
                "Payments", "record_payment",
                amount=booking.deposit_amount,
            ))
        elif native_workflow and has_payment and not booking_form_complete:
            queues["forms_waiting"].append(item(
                booking, "Wedding Booking Form has not been submitted",
                "Journey", "review_forms",
            ))
        elif native_workflow and booking_form_complete and not agreement_complete:
            queues["agreements_waiting"].append(item(
                booking,
                "Couple signed · your countersignature is needed" if contract else "Agreement has not been signed",
                "Journey", "countersign" if contract else "review_forms",
            ))

        for invoice in booking.invoices:
            if invoice.status in ("paid", "void", "cancelled"):
                continue
            balance = Decimal(invoice.total or 0) - Decimal(invoice.paid or 0)
            due = effective_invoice_due_date(invoice)
            if balance <= 0 or not due:
                continue
            detail = f"{invoice.number} · {money(balance):,.2f} remaining"
            target = ("overdue_payments" if due < today else
                      "payments_due" if due <= payments_due_through else None)
            if target:
                queues[target].append(item(
                    booking, detail, "Payments", "record_payment", due=due, amount=balance,
                ))

        for task in booking.tasks:
            if (task.workflow_key == "wbm_final_details_call" and not task.completed
                    and task.due_at and task.due_at.date() <= final_calls_due_through):
                queues["final_calls"].append(item(
                    booking, "Private 30-day final-details telephone call",
                    "Overview", "open_task", due=task.due_at.date(),
                ))

    queues["client_updates"].sort(
        key=lambda row: row["occurred_at"] or "", reverse=True
    )
    for key in ("overdue_payments", "payments_due", "final_calls"):
        queues[key].sort(key=lambda row: row["due_date"] or "9999-12-31")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queues": queues,
        "counts": {key: len(rows) for key, rows in queues.items()},
    }


@app.get("/api/bookings")
def list_bookings(brand: Brand | None = None, kind: RecordKind | None = None,
                  archived: bool = False, q: str | None = Query(default=None, max_length=100),
                  _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(Booking).options(selectinload(Booking.client)).order_by(Booking.event_date.asc().nullslast(), Booking.created_at.desc())
    stmt = stmt.where(Booking.archived_at.is_not(None) if archived else Booking.archived_at.is_(None))
    if brand:
        stmt = stmt.where(Booking.brand == brand)
    if kind:
        stmt = stmt.where(Booking.kind == kind)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.join(Client).where(or_(Booking.title.ilike(term), Booking.venue_or_project.ilike(term),
                                           Client.email.ilike(term), Client.company_name.ilike(term)))
    return [booking_json(x) for x in db.scalars(stmt).unique().all()]


@app.post("/api/bookings", status_code=201)
def create_booking(payload: BookingIn, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    client = Client(**payload.client.model_dump())
    db.add(client)
    db.flush()
    booking = Booking(**payload.model_dump(exclude={"client"}), client_id=client.id)
    db.add(booking)
    db.flush()
    create_default_tasks(db, booking.id, booking.kind, booking.event_date)
    audit(db, "create", "booking", booking.id, {"title": booking.title, "brand": booking.brand.value})
    db.commit()
    sync_booking_calendar_safely(db, booking)
    return get_booking(booking.id, _, db)


@app.get("/api/bookings/{booking_id}")
def get_booking(booking_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = full_booking(db, booking_id)
    activity = db.scalars(select(AuditLog).where(AuditLog.entity_id == booking_id)
                          .order_by(AuditLog.created_at.desc())).all()
    return booking_json(item, full=True, activity=activity)


@app.patch("/api/bookings/{booking_id}")
def patch_booking(booking_id: str, payload: BookingPatch, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = db.get(Booking, booking_id)
    if not item:
        raise HTTPException(404, "Record not found")
    values = payload.model_dump(exclude_unset=True)
    requested_status = values.get("status")
    if requested_status == RecordStatus.CANCELLED and item.status != RecordStatus.CANCELLED:
        raise HTTPException(409, "Use Cancel record so links, tasks and the cancellation reason are handled safely")
    if (item.status == RecordStatus.CANCELLED and requested_status is not None
            and requested_status != RecordStatus.CANCELLED):
        raise HTTPException(409, "Use Reopen record so the previous status and tasks are restored safely")
    client_values = values.pop("client", None)
    for key, value in values.items():
        setattr(item, key, value)
    if client_values:
        client = db.get(Client, item.client_id)
        for key, value in client_values.items():
            setattr(client, key, value)
    if "event_date" in values and "balance_due_date" not in values:
        refresh_wedding_payment_dates(db, item)
    elif "balance_due_date" in values:
        # Keep the older Edit booking route consistent with the dedicated
        # invoice control. The Payments screen remains the clearer route.
        agreed_due = values["balance_due_date"]
        for invoice in db.scalars(select(Invoice).where(
                Invoice.booking_id == item.id,
                ~Invoice.status.in_(["paid", "void", "cancelled"]))).all():
            invoice.due_date = agreed_due
            if agreed_due:
                replace_final_schedule_due_date(invoice, agreed_due)
                replace_balance_note(invoice, agreed_due)
    if "event_date" in values:
        sync_final_details_call_task(db, item)
    auto_confirmed = confirm_when_paid(item)
    audit(db, "update", "booking", item.id,
          {"fields": list(payload.model_fields_set), "auto_confirmed": auto_confirmed})
    db.commit()
    sync_booking_calendar_safely(db, item)
    return get_booking(item.id, _, db)


@app.post("/api/bookings/{booking_id}/archive")
def archive_booking(booking_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = db.get(Booking, booking_id)
    if not item:
        raise HTTPException(404, "Record not found")
    item.archived_at = datetime.now(timezone.utc)
    audit(db, "archive", "booking", item.id)
    db.commit()
    return {"ok": True}


@app.post("/api/bookings/{booking_id}/restore")
def restore_booking(booking_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = db.get(Booking, booking_id)
    if not item:
        raise HTTPException(404, "Record not found")
    item.archived_at = None
    audit(db, "restore", "booking", item.id)
    db.commit()
    return {"ok": True}


@app.get("/api/tasks")
def list_tasks(brand: Brand | None = None, include_completed: bool = True,
               _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(Task).options(selectinload(Task.booking)).join(Booking).where(
        Booking.archived_at.is_(None), Booking.status != RecordStatus.CANCELLED,
        visible_task_condition())
    if brand:
        stmt = stmt.where(Booking.brand == brand)
    if not include_completed:
        stmt = stmt.where(Task.completed.is_(False))
    stmt = stmt.order_by(Task.completed, Task.due_at.asc().nullslast(), Task.created_at)
    return [task_json(t) for t in db.scalars(stmt).all()]


@app.post("/api/bookings/{booking_id}/tasks", status_code=201)
def create_task(booking_id: str, payload: TaskIn, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if not db.get(Booking, booking_id):
        raise HTTPException(404, "Record not found")
    task = Task(booking_id=booking_id, **payload.model_dump())
    db.add(task)
    db.flush()
    audit(db, "create_task", "booking", booking_id, {"title": task.title})
    db.commit()
    db.refresh(task)
    return task_json(task)


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: str, payload: TaskPatch, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    audit(db, "update_task", "booking", task.booking_id, {"title": task.title})
    db.commit()
    db.refresh(task)
    return task_json(task)


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    booking_id, title = task.booking_id, task.title
    db.delete(task)
    audit(db, "delete_task", "booking", booking_id, {"title": title})
    db.commit()


@app.post("/api/bookings/{booking_id}/notes", status_code=201)
def create_note(booking_id: str, payload: NoteIn, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if not db.get(Booking, booking_id):
        raise HTTPException(404, "Record not found")
    note = BookingNote(booking_id=booking_id, body=payload.body.strip())
    db.add(note)
    db.flush()
    audit(db, "add_note", "booking", booking_id)
    db.commit()
    return {"id": note.id, "body": note.body, "created_at": note.created_at.isoformat()}


@app.delete("/api/notes/{note_id}", status_code=204)
def delete_note(note_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    note = db.get(BookingNote, note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    booking_id = note.booking_id
    db.delete(note)
    audit(db, "delete_note", "booking", booking_id)
    db.commit()


@app.get("/api/invoices")
def list_invoices(brand: Brand | None = None, archived: bool = False,
                  _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    # Keep the day-to-day payment register useful after the complete Studio
    # Ninja archive is imported. Historic invoices remain available inside
    # their archived records and through ?archived=true, but do not swamp the
    # active balances screen.
    stmt = (select(Invoice)
            .join(Booking)
            .options(selectinload(Invoice.booking), selectinload(Invoice.payments))
            .where(Booking.archived_at.is_not(None) if archived else Booking.archived_at.is_(None)))
    if brand:
        stmt = stmt.where(Invoice.brand == brand)
    rows = list(db.scalars(stmt).all())

    def due_order(item: Invoice) -> tuple:
        balance = Decimal("0") if item.status in ("void", "cancelled") else item.total - item.paid
        due = effective_invoice_due_date(item)
        if balance <= 0:
            return (3, date.max, -item.sequence)
        if not due:
            return (2, date.max, -item.sequence)
        if due < date.today():
            # Overdue first, with the nearest missed date at the top.
            return (0, -due.toordinal(), -item.sequence)
        # Then upcoming balances from the nearest due date onwards.
        return (1, due.toordinal(), -item.sequence)

    rows.sort(key=due_order)
    return [invoice_json(item) for item in rows]


@app.post("/api/bookings/{booking_id}/invoices", status_code=201)
def create_invoice(booking_id: str, payload: InvoiceIn, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Record not found")
    if payload.paid > payload.total:
        raise HTTPException(422, "Paid amount cannot exceed invoice total")
    sequence, number = next_invoice_number(db, booking.brand)
    values = payload.model_dump()
    invoice = Invoice(booking_id=booking.id, brand=booking.brand, sequence=sequence, number=number,
                      status=invoice_status(payload.total, payload.paid), **values)
    db.add(invoice)
    db.flush()
    if payload.paid > 0:
        booking.deposit_amount = max(booking.deposit_amount or Decimal("0"), payload.paid)
        booking.deposit_paid_date = booking.deposit_paid_date or payload.issue_date
        auto_confirmed = confirm_when_paid(booking)
        db.add(Payment(invoice_id=invoice.id, amount=payload.paid,
                       paid_date=booking.deposit_paid_date or payload.issue_date,
                       payment_type="bank_transfer", reference=number, notes="Opening payment"))
    else:
        auto_confirmed = False
    audit(db, "create_invoice", "booking", booking.id,
          {"number": number, "auto_confirmed": auto_confirmed})
    db.commit()
    return invoice_json(full_invoice(db, invoice.id))


def full_invoice(db: Session, invoice_id: str) -> Invoice:
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.booking).selectinload(Booking.client),
                                               selectinload(Invoice.payments)).where(Invoice.id == invoice_id))
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    return invoice


def replace_final_schedule_due_date(invoice: Invoice, due_date: date) -> None:
    """Keep an imported instalment schedule consistent with an agreed final date."""
    schedule = [dict(item) for item in (invoice.payment_schedule or [])]
    if not schedule:
        return
    labelled = [index for index, item in enumerate(schedule)
                if any(word in str(item.get("label") or "").lower()
                       for word in ("balance", "final", "remaining"))]
    candidates = labelled or list(range(len(schedule)))

    def schedule_date(index: int) -> date:
        raw = schedule[index].get("due_date")
        try:
            return date.fromisoformat(str(raw)) if raw else date.min
        except ValueError:
            return date.min

    final_index = max(candidates, key=schedule_date)
    schedule[final_index]["due_date"] = due_date.isoformat()
    invoice.payment_schedule = schedule


def replace_balance_note(invoice: Invoice, due_date: date) -> None:
    """Prevent a generated invoice note from showing the superseded date."""
    if invoice.notes:
        invoice.notes = re.sub(
            r"The remaining balance is due by [^.]+\.",
            f"The remaining balance is due by {due_date.strftime('%d %B %Y')}.",
            invoice.notes,
        )


@app.patch("/api/invoices/{invoice_id}/due-date")
def change_invoice_due_date(invoice_id: str, payload: InvoiceDueDatePatch,
                            _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    """Record a one-couple payment extension without changing the wedding date."""
    invoice = full_invoice(db, invoice_id)
    if invoice.status in ("void", "cancelled"):
        raise HTTPException(409, "The payment date cannot be changed on a closed invoice")
    previous_due = invoice.due_date or standard_wedding_due_date(invoice)
    invoice.due_date = payload.due_date
    replace_final_schedule_due_date(invoice, payload.due_date)
    replace_balance_note(invoice, payload.due_date)
    if (invoice.booking and invoice.booking.brand == Brand.WBM
            and invoice.booking.kind == RecordKind.WEDDING):
        # Reminders are intentionally booking-scoped, so the agreed invoice
        # date becomes this couple's reminder date without affecting anyone else.
        invoice.booking.balance_due_date = payload.due_date
    audit(db, "change_invoice_due_date", "booking", invoice.booking_id, {
        "invoice_id": invoice.id,
        "invoice_number": invoice.number,
        "previous_due_date": previous_due.isoformat() if previous_due else None,
        "new_due_date": payload.due_date.isoformat(),
        "reason": payload.reason,
    })
    db.commit()
    return invoice_json(full_invoice(db, invoice.id))


@app.post("/api/invoices/{invoice_id}/payments", status_code=201)
def create_payment(invoice_id: str, payload: PaymentIn, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    invoice = full_invoice(db, invoice_id)
    if invoice.status in ("void", "cancelled"):
        raise HTTPException(409, "A payment cannot be added to a closed invoice")
    if payload.amount > invoice.total - invoice.paid:
        raise HTTPException(422, "Payment cannot exceed the outstanding balance")
    payment = Payment(invoice_id=invoice.id, **payload.model_dump())
    db.add(payment)
    invoice.paid += payload.amount
    invoice.status = invoice_status(invoice.total, invoice.paid)
    auto_confirmed = False
    if invoice.booking:
        if not invoice.booking.deposit_paid_date:
            invoice.booking.deposit_paid_date = payload.paid_date
        if money(invoice.booking.deposit_amount) <= 0:
            invoice.booking.deposit_amount = payload.amount
        # Any first genuine payment secures an enquiry, even when it is
        # only part of the requested booking fee (for example £50 of £100).
        auto_confirmed = confirm_when_paid(invoice.booking)
    audit(db, "record_payment", "booking", invoice.booking_id,
          {"invoice": invoice.number, "amount": money(payload.amount), "auto_confirmed": auto_confirmed})
    db.commit()

    invoice = full_invoice(db, invoice.id)
    booking = invoice.booking
    sync_booking_calendar_safely(db, booking)
    payment_email_sent = False
    payment_email_error = None
    payment_email_paused = not automations_allowed(booking)
    template = db.scalar(select(EmailTemplate).where(
        EmailTemplate.brand == invoice.brand,
        EmailTemplate.template_key == "payment_received",
        EmailTemplate.is_active.is_(True),
    ))
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == invoice.brand))
    if payment_email_paused:
        payment_email_error = "Client emails are paused for this imported booking"
    elif not template:
        payment_email_error = "The payment confirmation template is missing or inactive"
    elif not profile:
        payment_email_error = "The business profile is missing"
    elif not smtp_ready(invoice.brand):
        payment_email_error = f"SMTP is not configured for {invoice.brand.value}"
    else:
        raw, _ = issue_portal_token(
            db, booking.id, portal_lifetime_days(booking)
        )
        portal_url = f"{settings.app_url.rstrip('/')}/client/{raw}?tab=invoices"
        outstanding = max(Decimal("0"), invoice.total - invoice.paid)
        deposit_remaining = max(Decimal("0"), booking.deposit_amount - invoice.paid)
        try:
            subject, email_body = send_booking_template_email(
                db, booking,
                profile,
                template,
                portal_url,
                extra_values={
                    "payment_amount": f"£{money(payload.amount):,.2f}",
                    "payment_date": payload.paid_date.strftime("%d %B %Y"),
                    "invoice_number": invoice.number,
                    "total_paid": f"£{money(invoice.paid):,.2f}",
                    "deposit_remaining": f"£{money(deposit_remaining):,.2f}",
                    "outstanding_balance": f"£{money(outstanding):,.2f}",
                    "payment_status": ("Paid in full" if outstanding <= 0
                                       else "Your booking is secured"),
                },
            )
            db.add(EmailLog(booking_id=booking.id, template_key="payment_received",
                            recipient=client_email_recipient(db, booking), subject=subject,
                            body=email_body, status="sent"))
            payment_email_sent = True
        except Exception as exc:
            payment_email_error = str(exc)
            db.add(EmailLog(booking_id=booking.id, template_key="payment_received",
                            recipient=client_email_recipient(db, booking), subject=template.subject,
                            status="failed", error=payment_email_error[:2000]))
        db.commit()

    result = invoice_json(full_invoice(db, invoice.id))
    result.update({"payment_email_sent": payment_email_sent,
                   "payment_email_error": payment_email_error,
                   "payment_email_paused": payment_email_paused})
    return result


@app.delete("/api/payments/{payment_id}", status_code=204)
def delete_payment(payment_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    if payment.legacy_source == "studio_ninja":
        raise HTTPException(409, "Imported Studio Ninja payment history is retained and cannot be deleted")
    invoice = db.get(Invoice, payment.invoice_id)
    if invoice.status in ("void", "cancelled"):
        raise HTTPException(409, "Payment history on a closed invoice is retained")
    invoice.paid = max(Decimal("0"), invoice.paid - payment.amount)
    invoice.status = invoice_status(invoice.total, invoice.paid)
    db.delete(payment)
    audit(db, "delete_payment", "booking", invoice.booking_id, {"invoice": invoice.number})
    db.commit()


@app.get("/api/invoices/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: str, inline: bool = Query(False),
                         _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    invoice = full_invoice(db, invoice_id)
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == invoice.brand))
    return Response(invoice_pdf(invoice, profile), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'{"inline" if inline else "attachment"}; filename="{invoice.number}.pdf"'})


@app.get("/api/invoices/{invoice_id}/receipt.pdf")
def download_receipt_pdf(invoice_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    invoice = full_invoice(db, invoice_id)
    if invoice.paid <= 0:
        raise HTTPException(422, "Record a payment before creating a receipt")
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == invoice.brand))
    return Response(invoice_pdf(invoice, profile, receipt=True), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{invoice.number}-receipt.pdf"'})


@app.get("/api/documents")
def list_documents(brand: Brand | None = None, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(Document).options(selectinload(Document.booking)).join(Booking).where(Booking.archived_at.is_(None))
    if brand:
        stmt = stmt.where(Booking.brand == brand)
    stmt = stmt.order_by(Document.created_at.desc())
    return [document_json(d) for d in db.scalars(stmt).all()]


@app.post("/api/bookings/{booking_id}/documents", status_code=201)
def upload_document(
    booking_id: str,
    category: str = Query(pattern="^[a-zA-Z0-9_-]{2,60}$"),
    source_system: str | None = Query(default=None, max_length=60),
    legacy_document_type: str | None = Query(default=None, max_length=80),
    legacy_reference: str | None = Query(default=None, max_length=160),
    document_date: date | None = Query(default=None),
    client_visible: bool = Query(default=False),
    file: UploadFile = File(...),
    _: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    if not db.get(Booking, booking_id):
        raise HTTPException(404, "Record not found")
    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if content_type not in ALLOWED_UPLOADS:
        raise HTTPException(415, "Only PDF, DOCX, JPEG and PNG files are accepted")
    original = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(file.filename or "document").name)[:200]
    storage_name = f"{booking_id}/{category}/{uuid.uuid4().hex}{Path(original).suffix.lower()}"
    target = settings.storage_root / storage_name
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with target.open("wb") as output:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                output.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {settings.max_upload_mb}MB limit")
            output.write(chunk)
    document = Document(booking_id=booking_id, category=category, original_name=original,
                        storage_name=storage_name, content_type=content_type, size_bytes=size,
                        source_system=source_system,
                        legacy_document_type=legacy_document_type,
                        legacy_reference=legacy_reference,
                        document_date=document_date,
                        is_client_visible=client_visible)
    db.add(document)
    db.flush()
    audit(db, "upload_document", "booking", booking_id, {
        "name": original, "category": category, "source_system": source_system,
        "client_visible": client_visible,
    })
    db.commit()
    return document_json(document)


@app.get("/api/documents/{document_id}")
def download_document(document_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    path = settings.storage_root / document.storage_name
    if not path.is_file():
        raise HTTPException(404, "Stored file is missing")
    return FileResponse(path, media_type=document.content_type, filename=document.original_name)


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    if document.source_system == "studio_ninja":
        raise HTTPException(409, "Original Studio Ninja documents are retained and cannot be deleted")
    path = settings.storage_root / document.storage_name
    booking_id, name = document.booking_id, document.original_name
    db.delete(document)
    audit(db, "delete_document", "booking", booking_id, {"name": name})
    db.commit()
    path.unlink(missing_ok=True)
    parent = path.parent
    if parent.exists() and not any(parent.iterdir()):
        shutil.rmtree(parent)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_portal_token(db: Session, booking_id: str, expires_days: int = 365) -> tuple[str, ClientPortalToken]:
    raw = secrets.token_urlsafe(32)
    row = ClientPortalToken(booking_id=booking_id, token_hash=token_digest(raw),
                            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days))
    db.add(row)
    db.flush()
    return raw, row


def resolve_portal(db: Session, token: str) -> ClientPortalToken:
    row = db.scalar(select(ClientPortalToken).options(selectinload(ClientPortalToken.booking).selectinload(Booking.client))
                    .where(ClientPortalToken.token_hash == token_digest(token),
                           ClientPortalToken.revoked_at.is_(None),
                           ClientPortalToken.expires_at > datetime.now(timezone.utc)))
    if not row:
        raise HTTPException(404, "This booking link is invalid or has expired")
    if row.booking.status == RecordStatus.CANCELLED:
        raise HTTPException(404, "This booking link is no longer active")
    return row


def portal_status_json(db: Session, booking: Booking) -> dict:
    submissions = db.scalars(select(FormSubmission).where(FormSubmission.booking_id == booking.id)).all()
    acceptance = db.scalar(select(ContractAcceptance).where(ContractAcceptance.booking_id == booking.id))
    logs = db.scalars(select(EmailLog).where(EmailLog.booking_id == booking.id)
                      .order_by(EmailLog.sent_at.desc()).limit(100)).all()
    quote = db.scalar(select(Quote).where(Quote.booking_id == booking.id)
                      .order_by(Quote.created_at.desc()).limit(1))
    quote_data = quote_json(quote)
    if quote_data and quote.invoice_id:
        invoice = db.get(Invoice, quote.invoice_id)
        quote_data["invoice_number"] = invoice.number if invoice else None
    client_templates = db.scalars(select(EmailTemplate).where(
        EmailTemplate.brand == booking.brand,
        EmailTemplate.is_active.is_(True),
        EmailTemplate.template_key.notin_(("new_enquiry_admin", "contract_completed")),
    ).order_by(EmailTemplate.display_name)).all()
    final_submission = next((x for x in submissions if x.form_type == FINAL_TIMINGS_FORM_TYPE), None)
    final_workflow = (booking.workflow_state or {}).get("final_timings_review") or {}
    return {
        "submissions": [{"id": x.id, "form_type": x.form_type, "data": x.data,
                         "submission_source": x.submission_source,
                         "source_document_id": x.source_document_id,
                         "submitted_at": x.submitted_at.isoformat(),
                         "updated_at": x.updated_at.isoformat()} for x in submissions],
        "contract": (contract_acceptance_json(acceptance) if acceptance else None),
        "emails": [{"template_key": x.template_key, "recipient": x.recipient, "subject": x.subject,
                    "status": x.status, "error": x.error,
                    "link_tracking_enabled": bool(x.tracking_token_hash),
                    "first_link_accessed_at": (x.first_link_accessed_at.isoformat()
                                                if x.first_link_accessed_at else None),
                    "last_link_accessed_at": (x.last_link_accessed_at.isoformat()
                                               if x.last_link_accessed_at else None),
                    "link_access_count": int(x.link_access_count or 0),
                    "sent_at": x.sent_at.isoformat()} for x in logs],
        "quote": quote_data,
        "quote_preparation": quote_preparation_json(booking),
        "automation_suppressed": booking.automation_suppressed,
        "final_details_unlocked": final_details_unlocked(db, booking),
        "final_timings": {
            "available": final_timings_unlocked(db, booking),
            "submitted": bool(final_submission),
            "submitted_at": (final_submission.submitted_at.isoformat()
                             if final_submission else None),
            "updated_at": (final_submission.updated_at.isoformat()
                           if final_submission else None),
            "pdf_document_id": (final_submission.source_document_id
                                if final_submission else None),
            "reviewed_at": final_workflow.get("reviewed_at"),
            "reviewed_by": final_workflow.get("reviewed_by"),
            "coverage": booking_coverage_allowance(db, booking),
        },
        "email_templates": [{"template_key": item.template_key,
                             "display_name": item.display_name}
                            for item in client_templates],
    }


def contract_acceptance_json(acceptance: ContractAcceptance) -> dict:
    return {
        "accepted_name": acceptance.accepted_name,
        "accepted_email": acceptance.accepted_email,
        "accepted_at": acceptance.accepted_at.isoformat(),
        "version": acceptance.contract_version,
        "acceptance_source": acceptance.acceptance_source,
        "source_detail": acceptance.source_detail,
        "is_legacy_import": acceptance.is_legacy_import,
        "supplier_signed_name": acceptance.supplier_signed_name,
        "supplier_signed_at": (acceptance.supplier_signed_at.isoformat()
                               if acceptance.supplier_signed_at else None),
        "supplier_signature_method": acceptance.supplier_signature_method,
        "fully_signed": bool(acceptance.is_legacy_import or acceptance.supplier_signed_at),
    }


def quote_preparation_json(booking: Booking) -> dict:
    raw = (booking.workflow_state or {}).get("quote_preparation") or {}
    return {
        "required_addons": [item for item in (raw.get("required_addons") or []) if isinstance(item, dict)],
        "discounts": [item for item in (raw.get("discounts") or []) if isinstance(item, dict)],
    }


def require_booking_journey_unlocked(db: Session, booking: Booking) -> None:
    """Website enquiries complete forms only after accepting a package quote."""
    if (booking.kind != RecordKind.WEDDING
            or booking.status not in (RecordStatus.ENQUIRY, RecordStatus.QUOTED)):
        return
    accepted_quote = db.scalar(select(Quote.id).where(
        Quote.booking_id == booking.id, Quote.status == "accepted"
    ).limit(1))
    if not accepted_quote:
        raise HTTPException(
            409,
            "Please choose and accept your package before completing the booking form or contract",
        )


WBM_TEMPLATE_USAGE: dict[str, tuple[str, str]] = {
    "quote": ("action", "Used when you press Prepare & send quote"),
    "booking_link": ("manual", "Manual option when you deliberately send a booking link"),
    "contract_reminder": ("manual", "Manual reminder offered when the form is complete but the agreement is unsigned"),
    "quote_followup_1": ("automatic", "Automatic quote follow-up one day after a successful quote"),
    "quote_followup_final": ("automatic", "Automatic final quote follow-up nine days after a successful quote"),
    "deposit_due_1": ("automatic", "Automatic booking-fee reminder on its due date"),
    "check_in_120": ("automatic", "Automatic friendly check-in 120 days before the wedding"),
    "check_in_30": ("automatic", "Automatic final-timings invitation 30 days before the wedding, including the Monday telephone-call date. This is the only automatic email permitted for eligible Studio Ninja imports after 20 October 2026"),
    "balance_due_7": ("automatic", "Automatic final-balance reminder seven days before it is due"),
    "balance_due_1": ("automatic", "Automatic final-balance reminder one day before it is due"),
    "balance_overdue_2": ("automatic", "Automatic overdue reminder every two days while a balance remains"),
    "payment_received": ("action", "Used when you record a payment and its confirmation is sent"),
    "enquiry_received": ("automatic", "Automatic acknowledgement after a website enquiry"),
    "new_enquiry_admin": ("automatic", "Automatic private notification to Mark after a website enquiry"),
    "quote_accepted": ("automatic", "Automatic confirmation after the couple accepts their package"),
    "contract_completed": ("automatic", "Automatic confirmation after both agreement signatures; manually retryable"),
    "final_questionnaire": ("obsolete", "Not used - final details are completed by telephone"),
    "balance_due_14": ("obsolete", "Not used - replaced by the seven-day balance reminder"),
    "balance_due_10": ("obsolete", "Not used - replaced by the seven-day balance reminder"),
}


def email_template_usage(template: EmailTemplate) -> dict:
    if template.brand == Brand.WBM:
        kind, label = WBM_TEMPLATE_USAGE.get(
            template.template_key,
            ("manual", "Custom manual option available from Email client"),
        )
    else:
        kind, label = ("manual", "Available when you deliberately email this client")
    if not template.is_active:
        return {
            "usage_kind": "inactive",
            "usage_label": f"Inactive - nothing can send this template. {label}",
        }
    return {"usage_kind": kind, "usage_label": label}


@app.get("/api/communications/templates")
def list_templates(brand: Brand | None = None, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(EmailTemplate).order_by(EmailTemplate.brand, EmailTemplate.display_name)
    if brand:
        stmt = stmt.where(EmailTemplate.brand == brand)
    rows = db.scalars(stmt).all()
    contracts = db.scalars(select(ContractTemplate).order_by(ContractTemplate.brand)).all()
    wbm_username, _ = smtp_credentials(Brand.WBM)
    ivory_username, _ = smtp_credentials(Brand.IVORY)
    return {"smtp_configured": smtp_ready(),
            "smtp_by_brand": {
                "wbm": {"configured": smtp_ready(Brand.WBM), "username": wbm_username},
                "ivory": {"configured": smtp_ready(Brand.IVORY), "username": ivory_username},
            }, "reminders_enabled": settings.reminders_enabled,
            "templates": [{"id": x.id, "brand": x.brand.value, "template_key": x.template_key,
                           "display_name": x.display_name, "subject": x.subject, "body": x.body,
                           "is_active": x.is_active, **email_template_usage(x)} for x in rows],
            "contracts": [{"id": x.id, "brand": x.brand.value, "title": x.title, "version": x.version,
                           "body": x.body, "is_active": x.is_active} for x in contracts]}


def template_preview_booking(db: Session, brand: Brand) -> Booking:
    booking = db.scalar(select(Booking).options(selectinload(Booking.client))
                        .where(Booking.brand == brand)
                        .order_by(Booking.created_at.desc()).limit(1))
    if booking:
        return booking
    wedding = brand == Brand.WBM
    example = Booking(brand=brand, kind=RecordKind.WEDDING if wedding else RecordKind.DIGITAL,
                      status=RecordStatus.ENQUIRY,
                      title="Sophie & James" if wedding else "Example Website Client",
                      event_date=date.today() + timedelta(days=180) if wedding else None,
                      venue_or_project="Peckforton Castle" if wedding else "Website design project",
                      package_name="Gold Package" if wedding else "Website Design",
                      quoted_total=Decimal("899") if wedding else Decimal("399"),
                      deposit_amount=Decimal("100") if wedding else Decimal("0"))
    example.client = Client(first_name="Sophie" if wedding else "Chris", last_name="Taylor",
                            partner_name="James" if wedding else None,
                            email="couple@example.com" if wedding else "client@example.com")
    return example


@app.get("/api/communications/templates/{template_id}/preview")
def preview_template(template_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    template = db.get(EmailTemplate, template_id)
    if not template:
        raise HTTPException(404, "Email template not found")
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == template.brand))
    if not profile:
        raise HTTPException(404, "Business profile not found")
    booking = template_preview_booking(db, template.brand)
    portal_url = f"{settings.app_url.rstrip('/')}/client/example-preview-link"
    subject, body, email_html = preview_template_email(booking, profile, template, portal_url)
    email_html = email_html.replace("cid:weddings-by-mark-logo", "/static/branding/weddings-by-mark-logo.png")
    email_html = email_html.replace("cid:weddings-by-mark-awards", "/static/branding/weddings-by-mark-awards.png")
    email_html = email_html.replace("cid:ivory-digital-logo", "/static/branding/ivory-digital-logo.png")
    return {"subject": subject, "body": body, "html": email_html,
            "test_recipient": profile.email or settings.admin_email,
            "brand": template.brand.value}


@app.post("/api/communications/templates/{template_id}/test")
def test_template(template_id: str, payload: TemplateTestIn, admin: Admin = Depends(current_admin),
                  db: Session = Depends(get_db)):
    template = db.get(EmailTemplate, template_id)
    if not template:
        raise HTTPException(404, "Email template not found")
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == template.brand))
    if not profile:
        raise HTTPException(404, "Business profile not found")
    booking = template_preview_booking(db, template.brand)
    try:
        subject, _ = send_template_email(
            booking, profile, template,
            f"{settings.app_url.rstrip('/')}/client/example-preview-link",
            recipient=str(payload.recipient),
        )
    except Exception as exc:
        raise HTTPException(503, str(exc))
    audit(db, "send_test_email", "email_template", template.id,
          {"recipient": str(payload.recipient), "admin": admin.email})
    db.commit()
    return {"ok": True, "subject": subject, "recipient": str(payload.recipient)}


@app.post("/api/communications/templates", status_code=201)
def create_template(payload: EmailTemplateIn, _: Admin = Depends(current_admin),
                    db: Session = Depends(get_db)):
    if db.scalar(select(EmailTemplate.id).where(
            EmailTemplate.brand == payload.brand,
            EmailTemplate.template_key == payload.template_key).limit(1)):
        raise HTTPException(409, "That template key already exists for this business")
    row = EmailTemplate(**payload.model_dump())
    db.add(row)
    db.flush()
    audit(db, "create_email_template", "email_template", row.id,
          {"key": row.template_key, "brand": row.brand.value})
    db.commit()
    return {"id": row.id, "brand": row.brand.value, "template_key": row.template_key,
            "display_name": row.display_name, "subject": row.subject, "body": row.body,
            "is_active": row.is_active}


@app.patch("/api/communications/templates/{template_id}")
def patch_template(template_id: str, payload: EmailTemplatePatch, _: Admin = Depends(current_admin),
                   db: Session = Depends(get_db)):
    row = db.get(EmailTemplate, template_id)
    if not row:
        raise HTTPException(404, "Email template not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    audit(db, "update_email_template", "email_template", row.id, {"key": row.template_key})
    db.commit()
    return {"ok": True}


@app.delete("/api/communications/templates/{template_id}", status_code=204)
def delete_template(template_id: str, _: Admin = Depends(current_admin),
                    db: Session = Depends(get_db)):
    row = db.get(EmailTemplate, template_id)
    if not row:
        raise HTTPException(404, "Email template not found")
    audit(db, "delete_email_template", "email_template", row.id,
          {"key": row.template_key, "brand": row.brand.value,
           "display_name": row.display_name})
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@app.patch("/api/communications/contracts/{contract_id}")
def patch_contract(contract_id: str, payload: ContractTemplatePatch, _: Admin = Depends(current_admin),
                   db: Session = Depends(get_db)):
    row = db.get(ContractTemplate, contract_id)
    if not row:
        raise HTTPException(404, "Contract template not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    audit(db, "update_contract_template", "contract_template", row.id, {"version": row.version})
    db.commit()
    return {"ok": True}


@app.get("/api/bookings/{booking_id}/portal")
def booking_portal_status(booking_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Record not found")
    return portal_status_json(db, booking)


@app.post("/api/bookings/{booking_id}/portal", status_code=201)
def create_portal_link(booking_id: str, payload: PortalCreateIn, _: Admin = Depends(current_admin),
                       db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Record not found")
    if booking.status == RecordStatus.CANCELLED:
        raise HTTPException(409, "Reopen the record before creating a new client portal link")
    manual_only = not automations_allowed(booking)
    if manual_only:
        if booking.legacy_source != "studio_ninja":
            raise HTTPException(409, "Client communication is paused for this booking")
        if payload.manual_confirmation != "CREATE MANUAL LINK":
            raise HTTPException(422, "Type CREATE MANUAL LINK exactly to confirm")
        if not payload.manual_reason or len(payload.manual_reason.strip()) < 3:
            raise HTTPException(422, "Add a short reason for creating this one-off link")
    raw, row = issue_portal_token(
        db, booking_id, max(payload.expires_days, portal_lifetime_days(booking))
    )
    audit(
        db,
        "create_manual_client_link" if manual_only else "create_client_link",
        "booking",
        booking_id,
        {
            "expires_at": row.expires_at.isoformat(),
            "manual_only": manual_only,
            "reason": payload.manual_reason.strip() if manual_only else None,
        },
    )
    db.commit()
    return {
        "url": f"{settings.app_url.rstrip('/')}/client/{raw}",
        "expires_at": row.expires_at.isoformat(),
        "manual_only": manual_only,
        "automation_suppressed": booking.automation_suppressed,
    }


@app.put("/api/bookings/{booking_id}/quote/preparation")
def save_quote_preparation(booking_id: str, payload: QuotePreparationIn,
                           _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Record not found")
    if booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING:
        raise HTTPException(422, "Quote preparation is only available for wedding bookings")
    if booking.status == RecordStatus.CANCELLED or not automations_allowed(booking):
        raise HTTPException(409, "This booking is not available for automatic quote preparation")
    if db.scalar(select(Quote.id).where(Quote.booking_id == booking.id,
                                        Quote.status == "accepted").limit(1)):
        raise HTTPException(409, "The accepted quote and invoice are locked")

    required_input = {item.addon_id: item for item in payload.required_addons}
    discount_input = {item.addon_id: item for item in payload.discounts}
    if set(required_input) & set(discount_input):
        raise HTTPException(422, "An item cannot be both an add-on and a discount")
    wanted_ids = list(required_input) + list(discount_input)
    rows = db.scalars(select(AddOnOption).where(
        AddOnOption.id.in_(wanted_ids), AddOnOption.brand == booking.brand,
        AddOnOption.is_active.is_(True),
    )).all() if wanted_ids else []
    if len(rows) != len(wanted_ids):
        raise HTTPException(422, "One or more selected quote items are unavailable")
    by_id = {row.id: row for row in rows}

    def snapshot(item_id: str, entered: QuotePreparationIn, discount: bool) -> dict:
        row = by_id[item_id]
        if bool(row.is_discount) != discount:
            raise HTTPException(422, f"{row.name} has the wrong quote item type")
        source = discount_input[item_id] if discount else required_input[item_id]
        return {"addon_id": row.id, "code": row.code, "name": row.name,
                "description": row.description, "price": money(source.price),
                "required": not discount, "discount": discount}

    preparation = {
        "required_addons": [snapshot(item_id, payload, False) for item_id in required_input],
        "discounts": [snapshot(item_id, payload, True) for item_id in discount_input],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    booking.workflow_state = {**(booking.workflow_state or {}), "quote_preparation": preparation}
    audit(db, "prepare_quote", "booking", booking.id,
          {"required_addons": len(required_input), "discounts": len(discount_input)})
    db.commit()
    return quote_preparation_json(booking)


@app.post("/api/bookings/{booking_id}/quote/send")
def create_and_send_quote(booking_id: str, payload: PortalCreateIn,
                          _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(Booking.id == booking_id))
    if not booking:
        raise HTTPException(404, "Record not found")
    if booking.status == RecordStatus.CANCELLED:
        raise HTTPException(409, "Reopen the record before sending another quote")
    if not automations_allowed(booking):
        raise HTTPException(409, "Client emails are paused for this imported booking")
    if booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING:
        raise HTTPException(422, "Package quotes are only available for Weddings By Mark bookings")
    if db.scalar(select(Quote).where(Quote.booking_id == booking.id, Quote.status == "accepted")):
        raise HTTPException(409, "This couple has already accepted their package quote")
    raw, row = issue_portal_token(
        db, booking.id, max(payload.expires_days, portal_lifetime_days(booking))
    )
    quote_url = f"{settings.app_url.rstrip('/')}/client/{raw}?tab=quote"
    tracking_token = secrets.token_urlsafe(32)
    tracked_quote_url = f"{quote_url}&email_access={tracking_token}"
    template = db.scalar(select(EmailTemplate).where(EmailTemplate.brand == Brand.WBM,
                                                     EmailTemplate.template_key == "quote",
                                                     EmailTemplate.is_active.is_(True)))
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == Brand.WBM))
    recipient = client_email_recipient(db, booking)
    email_log = EmailLog(
        booking_id=booking.id,
        template_key="quote",
        recipient=recipient,
        subject=(template.subject if template else "Wedding package quote"),
        status="sending",
        tracking_token_hash=token_digest(tracking_token),
    )
    db.add(email_log)
    email_sent, email_error, subject = False, None, None
    if not template:
        email_error = "The quote email template is missing or inactive"
        email_log.status = "failed"
        email_log.error = email_error
    elif not smtp_ready(Brand.WBM):
        email_error = "SMTP is not configured for Weddings By Mark"
        email_log.status = "failed"
        email_log.error = email_error
    else:
        try:
            subject, email_body = send_booking_template_email(
                db, booking, profile, template, tracked_quote_url
            )
            email_sent = True
            email_log.subject = subject
            email_log.body = email_body
            email_log.status = "sent"
            if booking.status == RecordStatus.ENQUIRY:
                booking.status = RecordStatus.QUOTED
            for task in db.scalars(select(Task).where(
                    Task.booking_id == booking.id,
                    or_(Task.workflow_key == "wbm_quote", Task.title.ilike("%quote%")))).all():
                task.completed = True
        except Exception as exc:
            email_error = str(exc)
            email_log.status = "failed"
            email_log.error = email_error[:2000]
    audit(db, "send_quote", "booking", booking.id,
          {"email_sent": email_sent, "expires_at": row.expires_at.isoformat()})
    db.commit()
    return {"url": quote_url, "expires_at": row.expires_at.isoformat(),
            "email_sent": email_sent, "email_error": email_error, "subject": subject}


@app.post("/api/bookings/{booking_id}/emails/send")
def send_booking_email(booking_id: str, payload: SendEmailIn, _: Admin = Depends(current_admin),
                       db: Session = Depends(get_db)):
    booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(Booking.id == booking_id))
    if not booking:
        raise HTTPException(404, "Record not found")
    if booking.status == RecordStatus.CANCELLED:
        raise HTTPException(409, "Reopen the cancelled booking before sending a client email")
    manual_only = not automations_allowed(booking)
    if manual_only:
        if booking.legacy_source != "studio_ninja":
            raise HTTPException(409, "Client communication is paused for this booking")
        if payload.manual_confirmation != "SEND ONE MANUAL EMAIL":
            raise HTTPException(422, "Type SEND ONE MANUAL EMAIL exactly to confirm")
        if not payload.manual_reason or len(payload.manual_reason.strip()) < 3:
            raise HTTPException(422, "Add a short reason for this one-off email")
    template = db.scalar(select(EmailTemplate).where(EmailTemplate.brand == booking.brand,
                                                     EmailTemplate.template_key == payload.template_key,
                                                     EmailTemplate.is_active.is_(True)))
    if not template:
        raise HTTPException(404, "Active email template not found")
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
    try:
        portal_url = issue_client_email_url(db, booking, template.template_key)
        recipient = client_email_recipient(db, booking)
        subject, email_body = send_booking_template_email(
            db, booking, profile, template, portal_url
        )
        log = EmailLog(booking_id=booking.id, template_key=template.template_key,
                       recipient=recipient, subject=subject, body=email_body, status="sent")
        db.add(log)
        audit(
            db,
            "send_manual_email" if manual_only else "send_email",
            "booking",
            booking.id,
            {
                "template": template.template_key,
                "manual_only": manual_only,
                "reason": payload.manual_reason.strip() if manual_only else None,
            },
        )
        db.commit()
        return {
            "ok": True,
            "subject": subject,
            "manual_only": manual_only,
            "automation_suppressed": booking.automation_suppressed,
        }
    except Exception as exc:
        db.add(EmailLog(booking_id=booking.id, template_key=template.template_key,
                        recipient=client_email_recipient(db, booking), subject=template.subject,
                        status="failed", error=str(exc)[:2000]))
        db.commit()
        raise HTTPException(503, str(exc))


@app.get("/api/bookings/{booking_id}/email-centre")
def client_email_centre(booking_id: str, _: Admin = Depends(current_admin),
                        db: Session = Depends(get_db)):
    """Return everything needed by the one-record email composer."""
    booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(
        Booking.id == booking_id
    ))
    if not booking:
        raise HTTPException(404, "Record not found")
    templates = list(db.scalars(select(EmailTemplate).where(
        EmailTemplate.brand == booking.brand,
        EmailTemplate.is_active.is_(True),
        EmailTemplate.template_key != "new_enquiry_admin",
    ).order_by(EmailTemplate.display_name)).all())
    available_keys = {item.template_key for item in templates}
    has_booking_form = bool(db.scalar(select(FormSubmission.id).where(
        FormSubmission.booking_id == booking.id,
        FormSubmission.form_type == "booking_form",
    ).limit(1)))
    has_contract = bool(db.scalar(select(ContractAcceptance.id).where(
        ContractAcceptance.booking_id == booking.id
    ).limit(1)))
    accepted_quote = db.scalar(select(Quote).where(
        Quote.booking_id == booking.id,
        Quote.status == "accepted",
    ).order_by(Quote.accepted_at.desc()).limit(1))
    if has_booking_form and not has_contract and "contract_reminder" in available_keys:
        recommended = "contract_reminder"
    elif accepted_quote and not booking.deposit_paid_date and "deposit_due_1" in available_keys:
        recommended = "deposit_due_1"
    elif not accepted_quote and "quote" in available_keys:
        recommended = "quote"
    elif "booking_link" in available_keys:
        recommended = "booking_link"
    else:
        recommended = templates[0].template_key if templates else None
    return {
        "booking_id": booking.id,
        "client_name": booking.title,
        "recipient": client_email_recipient(db, booking),
        "original_recipient": booking.client.email,
        "is_test": booking.is_test,
        "cancelled": booking.status == RecordStatus.CANCELLED,
        "manual_only": not automations_allowed(booking),
        "automation_suppressed": booking.automation_suppressed,
        "recommended_template_key": recommended,
        "account_link_included": True,
        "templates": [{
            "template_key": item.template_key,
            "display_name": item.display_name,
            "subject": item.subject,
            "body": item.body,
        } for item in templates],
    }


@app.post("/api/bookings/{booking_id}/email-centre/send")
def send_client_composed_email(booking_id: str, payload: ClientEmailComposeIn,
                               _: Admin = Depends(current_admin),
                               db: Session = Depends(get_db)):
    """Send one deliberate template-based or free-written client email."""
    booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(
        Booking.id == booking_id
    ))
    if not booking:
        raise HTTPException(404, "Record not found")
    if booking.status == RecordStatus.CANCELLED:
        raise HTTPException(409, "Reopen the cancelled booking before sending a client email")
    manual_only = not automations_allowed(booking)
    if manual_only:
        if booking.legacy_source != "studio_ninja":
            raise HTTPException(409, "Client communication is paused for this booking")
        if payload.manual_confirmation != "SEND ONE MANUAL EMAIL":
            raise HTTPException(422, "Type SEND ONE MANUAL EMAIL exactly to confirm")
        if not payload.manual_reason or len(payload.manual_reason.strip()) < 3:
            raise HTTPException(422, "Add a short reason for this one-off email")

    source_template = None
    if payload.mode == "template":
        if not payload.template_key:
            raise HTTPException(422, "Choose an email template")
        source_template = db.scalar(select(EmailTemplate).where(
            EmailTemplate.brand == booking.brand,
            EmailTemplate.template_key == payload.template_key,
            EmailTemplate.is_active.is_(True),
            EmailTemplate.template_key != "new_enquiry_admin",
        ))
        if not source_template:
            raise HTTPException(404, "Active client email template not found")

    template_key = source_template.template_key if source_template else "manual_client_email"
    composed = EmailTemplate(
        brand=booking.brand,
        template_key=template_key,
        display_name=(source_template.display_name if source_template else "Manual client email"),
        subject=payload.subject.strip(),
        body=payload.body.strip(),
        is_active=True,
    )
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
    if not profile:
        raise HTTPException(404, "Business profile not found")
    recipient = client_email_recipient(db, booking)
    try:
        portal_url = issue_client_email_url(db, booking, template_key)
        subject, email_body = send_booking_template_email(
            db, booking, profile, composed, portal_url
        )
        db.add(EmailLog(
            booking_id=booking.id,
            template_key=template_key,
            recipient=recipient,
            subject=subject,
            body=email_body,
            status="sent",
        ))
        audit(db, "send_manual_email" if manual_only else "send_client_email",
              "booking", booking.id, {
                  "mode": payload.mode,
                  "template": template_key,
                  "subject": subject,
                  "account_link_included": True,
                  "manual_only": manual_only,
                  "reason": payload.manual_reason.strip() if manual_only else None,
              })
        db.commit()
        return {
            "ok": True,
            "recipient": recipient,
            "subject": subject,
            "template_key": template_key,
            "account_link_included": True,
            "manual_only": manual_only,
            "automation_suppressed": booking.automation_suppressed,
        }
    except Exception as exc:
        db.add(EmailLog(
            booking_id=booking.id,
            template_key=template_key,
            recipient=recipient,
            subject=payload.subject.strip(),
            status="failed",
            error=str(exc)[:2000],
        ))
        db.commit()
        raise HTTPException(503, str(exc))


@app.get("/api/client/{token}")
def public_portal_data(
    token: str,
    email_access: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    portal = resolve_portal(db, token)
    booking = portal.booking
    if email_access:
        access_log = db.scalar(select(EmailLog).where(
            EmailLog.booking_id == booking.id,
            EmailLog.template_key == "quote",
            EmailLog.status == "sent",
            EmailLog.tracking_token_hash == token_digest(email_access),
        ).limit(1))
        if access_log:
            accessed_at = datetime.now(timezone.utc)
            first_access = access_log.first_link_accessed_at is None
            if first_access:
                access_log.first_link_accessed_at = accessed_at
            access_log.last_link_accessed_at = accessed_at
            access_log.link_access_count = int(access_log.link_access_count or 0) + 1
            if first_access:
                audit(db, "quote_link_accessed", "booking", booking.id, {
                    "email_log_id": access_log.id,
                    "recipient": access_log.recipient,
                })
            db.commit()
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
    contract = db.scalar(select(ContractTemplate).where(ContractTemplate.brand == booking.brand,
                                                        ContractTemplate.is_active.is_(True)))
    booking_form_template = (wedding_booking_template(db)
                             if booking.brand == Brand.WBM and booking.kind == RecordKind.WEDDING
                             and not booking.legacy_source else None)
    status_data = portal_status_json(db, booking)
    packages = db.scalars(select(PackageOption).where(PackageOption.brand == booking.brand,
                                                       PackageOption.is_active.is_(True))
                          .order_by(PackageOption.display_order, PackageOption.price)).all()
    addons = db.scalars(select(AddOnOption).where(AddOnOption.brand == booking.brand,
                                                  AddOnOption.is_active.is_(True),
                                                  AddOnOption.is_discount.is_(False))
                        .order_by(AddOnOption.display_order, AddOnOption.price)).all()
    client_invoices = db.scalars(select(Invoice).options(selectinload(Invoice.booking),
                                                          selectinload(Invoice.payments))
                                 .where(Invoice.booking_id == booking.id)
                                 .order_by(Invoice.sequence.desc())).all()
    client_documents = db.scalars(select(Document).where(
        Document.booking_id == booking.id,
        Document.is_client_visible.is_(True),
    ).order_by(Document.document_date.desc(), Document.created_at.desc())).all()
    return {"business": {"name": profile.display_name, "brand": profile.brand.value,
                         "email": profile.email, "phone": profile.phone},
            "record": {"title": booking.title, "kind": booking.kind.value,
                       "status": booking.status.value,
                       "event_date": booking.event_date.isoformat() if booking.event_date else None,
                       "venue_or_project": booking.venue_or_project, "venue_address": booking.venue_address,
                       "venue_place_id": booking.venue_place_id, "venue_lat": booking.venue_lat,
                       "venue_lng": booking.venue_lng, "package_name": booking.package_name,
                       "quoted_total": money(booking.quoted_total), "deposit_amount": money(booking.deposit_amount),
                       "payment_reference": payment_reference(booking),
                       "legacy_source": booking.legacy_source, "is_test": booking.is_test,
                       "client": client_json(booking.client)},
            "booking_form_template": (public_booking_form(booking_form_template.config or {})
                                      if booking_form_template else None),
            "contract_template": ({"title": contract.title, "version": contract.version, "body": contract.body}
                                  if contract else None),
            "catalog": {"packages": [package_json(x) for x in packages],
                        "addons": [addon_json(x) for x in addons]},
            "invoices": [invoice_json(x) for x in client_invoices],
            "documents": [document_json(x) for x in client_documents], **status_data}


def public_invoice_for_portal(db: Session, token: str, invoice_id: str) -> Invoice:
    portal = resolve_portal(db, token)
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.booking).selectinload(Booking.client),
                                                selectinload(Invoice.payments))
                        .where(Invoice.id == invoice_id, Invoice.booking_id == portal.booking_id))
    if not invoice:
        raise HTTPException(404, "Invoice not found for this booking")
    return invoice


@app.get("/api/client/{token}/invoices/{invoice_id}/invoice.pdf")
def public_invoice_pdf(token: str, invoice_id: str, inline: bool = Query(False),
                       db: Session = Depends(get_db)):
    invoice = public_invoice_for_portal(db, token, invoice_id)
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == invoice.brand))
    return Response(invoice_pdf(invoice, profile), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'{"inline" if inline else "attachment"}; filename="{invoice.number}.pdf"'})


@app.get("/api/client/{token}/invoices/{invoice_id}/receipt.pdf")
def public_receipt_pdf(token: str, invoice_id: str, db: Session = Depends(get_db)):
    invoice = public_invoice_for_portal(db, token, invoice_id)
    if invoice.paid <= 0:
        raise HTTPException(422, "A receipt is available after a payment has been recorded")
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == invoice.brand))
    return Response(invoice_pdf(invoice, profile, receipt=True), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{invoice.number}-receipt.pdf"'})


@app.get("/api/client/{token}/documents/{document_id}")
def public_legacy_document(token: str, document_id: str, db: Session = Depends(get_db)):
    portal = resolve_portal(db, token)
    document = db.scalar(select(Document).where(
        Document.id == document_id,
        Document.booking_id == portal.booking_id,
        Document.is_client_visible.is_(True),
    ))
    if not document:
        raise HTTPException(404, "Document not found for this booking")
    path = settings.storage_root / document.storage_name
    if not path.exists():
        raise HTTPException(404, "Document file is missing")
    return FileResponse(path, media_type=document.content_type, filename=document.original_name)


@app.post("/api/client/{token}/quote", status_code=201)
def accept_quote(token: str, payload: QuoteAcceptIn, db: Session = Depends(get_db)):
    if not payload.confirmed:
        raise HTTPException(422, "Please confirm the package and price before accepting")
    portal = resolve_portal(db, token)
    booking = portal.booking
    if booking.kind != RecordKind.WEDDING or booking.brand != Brand.WBM:
        raise HTTPException(422, "Package selection is only available for wedding bookings")
    existing = db.scalar(select(Quote).where(Quote.booking_id == booking.id,
                                             Quote.status == "accepted"))
    if existing:
        raise HTTPException(409, "This quote has already been accepted")
    package = db.scalar(select(PackageOption).where(PackageOption.id == payload.package_id,
                                                    PackageOption.brand == booking.brand,
                                                    PackageOption.is_active.is_(True)))
    if not package:
        raise HTTPException(404, "The selected package is no longer available")
    preparation = quote_preparation_json(booking)
    required_items = preparation["required_addons"]
    discount_items = preparation["discounts"]
    required_ids = [item["addon_id"] for item in required_items]
    discount_ids = [item["addon_id"] for item in discount_items]
    requested_ids = [item_id for item_id in dict.fromkeys(payload.addon_ids)
                     if item_id not in required_ids and item_id not in discount_ids]
    addons = db.scalars(select(AddOnOption).where(AddOnOption.id.in_(requested_ids),
                                                  AddOnOption.brand == booking.brand,
                                                  AddOnOption.is_active.is_(True),
                                                  AddOnOption.is_discount.is_(False))).all() if requested_ids else []
    if len(addons) != len(requested_ids):
        raise HTTPException(422, "One or more selected add-ons are unavailable")
    by_id = {x.id: x for x in addons}
    addons = [by_id[x] for x in requested_ids]
    for addon in addons:
        eligible = addon.eligible_package_codes or []
        if eligible and package.code not in eligible:
            raise HTTPException(422, f"{addon.name} is not available with {package.name}")
    line_items = [{"type": "package", "code": package.code, "name": package.name,
                   "description": package.description, "quantity": 1, "unit_price": money(package.price),
                   "total": money(package.price)}]
    for item in required_items:
        line_items.append({"type": "addon", "code": item["code"], "name": item["name"],
                           "description": item["description"], "quantity": 1,
                           "unit_price": money(item["price"]), "total": money(item["price"]),
                           "required": True})
    for addon in addons:
        line_items.append({"type": "addon", "code": addon.code, "name": addon.name,
                           "description": addon.description, "quantity": 1,
                           "unit_price": money(addon.price), "total": money(addon.price),
                           "required": False})
    for item in discount_items:
        amount = Decimal(str(item["price"]))
        line_items.append({"type": "discount", "code": item["code"], "name": item["name"],
                           "description": item["description"], "quantity": 1,
                           "unit_price": money(-amount), "total": money(-amount),
                           "discount": True})
    required_total = sum((Decimal(str(item["price"])) for item in required_items), Decimal("0"))
    discount_total = sum((Decimal(str(item["price"])) for item in discount_items), Decimal("0"))
    total = package.price + sum((x.price for x in addons), Decimal("0")) + required_total - discount_total
    if total < 0:
        raise HTTPException(422, "The discount cannot be greater than the quote total")
    accepted_on = date.today()
    deposit_due_date = accepted_on + timedelta(days=1)
    normal_balance_due = booking.event_date - timedelta(days=45) if booking.event_date else None
    balance_due_date = (max(normal_balance_due, deposit_due_date)
                        if normal_balance_due else None)
    initial_fee, balance_due_date, initial_schedule = schedule_rows(
        Decimal(total), Decimal(package.deposit_amount), "standard", accepted_on, booking.event_date
    )
    quote = Quote(booking_id=booking.id, status="accepted", package_id=package.id,
                  selected_addon_ids=required_ids + requested_ids + discount_ids,
                  line_items=line_items, total=total,
                  deposit_amount=initial_fee, accepted_at=datetime.now(timezone.utc))
    db.add(quote)
    db.flush()
    sequence, number = next_invoice_number(db, booking.brand)
    invoice = Invoice(booking_id=booking.id, brand=booking.brand, sequence=sequence, number=number,
                      issue_date=accepted_on, deposit_due_date=deposit_due_date,
                      supply_date=booking.event_date, due_date=balance_due_date,
                      description=package.name, total=total,
                      paid=Decimal("0"), status="unpaid", line_items=line_items,
                      payment_schedule=initial_schedule,
                      notes=(f"Booking fee of £{money(initial_fee):,.2f} is due by "
                             f"{deposit_due_date.strftime('%d %B %Y')}. "
                             + (f"The remaining balance is due by {balance_due_date.strftime('%d %B %Y')}."
                                if balance_due_date else "The final balance date will be confirmed once the wedding date is set.")))
    db.add(invoice)
    db.flush()
    quote.invoice_id = invoice.id
    booking.package_name = package.name
    booking.quoted_total = total
    booking.deposit_amount = initial_fee
    booking.balance_due_date = balance_due_date
    if booking.status == RecordStatus.ENQUIRY:
        booking.status = RecordStatus.QUOTED
    for task in db.scalars(select(Task).where(Task.booking_id == booking.id,
                                              Task.title.ilike("%quote%"))).all():
        task.completed = True
    acceptance_email_sent = False
    acceptance_template = db.scalar(select(EmailTemplate).where(
        EmailTemplate.brand == booking.brand, EmailTemplate.template_key == "quote_accepted",
        EmailTemplate.is_active.is_(True)))
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
    if (automations_allowed(booking) and acceptance_template and profile
            and smtp_ready(booking.brand)):
        try:
            invoice_portal_url = f"{settings.app_url.rstrip('/')}/client/{token}"
            subject, email_body = send_booking_template_email(
                db, booking, profile, acceptance_template, invoice_portal_url,
                extra_values={
                    "deposit_due_date": deposit_due_date.strftime("%d %B %Y"),
                    "balance_due_date": (balance_due_date.strftime("%d %B %Y")
                                         if balance_due_date else "to be confirmed"),
                },
            )
            db.add(EmailLog(booking_id=booking.id, template_key="quote_accepted",
                            recipient=client_email_recipient(db, booking), subject=subject,
                            body=email_body, status="sent"))
            acceptance_email_sent = True
        except Exception as exc:
            db.add(EmailLog(booking_id=booking.id, template_key="quote_accepted",
                            recipient=client_email_recipient(db, booking), subject=acceptance_template.subject,
                            status="failed", error=str(exc)[:2000]))
    audit(db, "accept_quote", "booking", booking.id,
          {"package": package.name, "addons": [x.name for x in addons],
           "total": money(total), "invoice": number,
           "acceptance_email_sent": acceptance_email_sent})
    db.commit()
    calendar_sync = sync_booking_calendar_safely(db, booking)
    return {"ok": True, "quote": quote_json(quote), "invoice": invoice_json(invoice),
            "acceptance_email_sent": acceptance_email_sent,
            "google_calendar": calendar_sync}


@app.post("/api/client/{token}/forms")
def submit_public_form(token: str, payload: PublicFormIn, db: Session = Depends(get_db)):
    portal = resolve_portal(db, token)
    booking = portal.booking
    require_booking_journey_unlocked(db, booking)
    form_values = dict(payload.data)
    form_snapshot = None
    form_template_updated_at = None
    if payload.form_type == FINAL_TIMINGS_FORM_TYPE:
        if not final_timings_unlocked(db, booking):
            raise HTTPException(409, "Your Final Wedding Timings Form opens 30 days before your wedding")
        try:
            form_values = validated_final_timings(db, booking, form_values)
        except ValidationError as exc:
            message = exc.errors()[0].get("msg", "Please check the timings form")
            raise HTTPException(422, str(message).removeprefix("Value error, ")) from exc
    if (payload.form_type == "booking_form" and booking.brand == Brand.WBM
            and booking.kind == RecordKind.WEDDING and not booking.legacy_source):
        template = wedding_booking_template(db)
        accepted, snapshot = validate_booking_answers(template.config or {}, form_values)
        form_values = accepted
        form_snapshot = snapshot
        form_template_updated_at = template.updated_at.isoformat()
    row = db.scalar(select(FormSubmission).where(FormSubmission.booking_id == booking.id,
                                                 FormSubmission.form_type == payload.form_type))
    if row:
        row.data = form_values
        row.updated_at = datetime.now(timezone.utc)
        row.submission_source = "client_portal_updated"
    else:
        row = FormSubmission(booking_id=booking.id, form_type=payload.form_type,
                             data=form_values, submission_source="client_portal")
        db.add(row)
    final_document = None
    if payload.form_type == "booking_form":
        previous_plan = payment_plan_code(booking)
        booking.form_data = {**form_values,
                             **({"_answer_snapshot": form_snapshot,
                                 "_form_template_updated_at": form_template_updated_at}
                                if form_snapshot is not None else {})}
        if form_values.get("primary_phone"):
            booking.client.phone = str(form_values["primary_phone"]).strip()
        if form_values.get("partner_full_name"):
            booking.client.partner_name = str(form_values["partner_full_name"]).strip()
        address_parts = [form_values.get(key) for key in ("street_address", "town", "county", "postcode")]
        address = ", ".join(str(value).strip() for value in address_parts if value)
        if address:
            booking.client.address = address
        if form_values.get("wedding_date"):
            try:
                booking.event_date = date.fromisoformat(str(form_values["wedding_date"]))
                sync_final_details_call_task(db, booking)
            except ValueError:
                pass
        if form_values.get("ceremony_details") and not booking.venue_or_project:
            booking.venue_or_project = str(form_values["ceremony_details"]).strip()[:240]
        if form_values.get("venue_name"):
            booking.venue_or_project = str(form_values["venue_name"]).strip()[:240]
        if form_values.get("venue_address"):
            booking.venue_address = str(form_values["venue_address"]).strip()[:1000]
        if form_values.get("venue_place_id"):
            booking.venue_place_id = str(form_values["venue_place_id"]).strip()[:255]
        if form_values.get("venue_lat") not in (None, ""):
            booking.venue_lat = float(form_values["venue_lat"])
        if form_values.get("venue_lng") not in (None, ""):
            booking.venue_lng = float(form_values["venue_lng"])
        accepted_quote = db.scalar(select(Quote).where(Quote.booking_id == booking.id,
                                                        Quote.status == "accepted"))
        if form_values.get("package_selected") and not accepted_quote:
            booking.package_name = str(form_values["package_selected"]).strip()[:160]
        chosen_plan = payment_plan_code(booking)
        apply_payment_plan(db, booking, chosen_plan)
        if chosen_plan != previous_plan:
            audit(db, "change_payment_plan", "booking", booking.id,
                  {"previous": previous_plan, "new": chosen_plan})
        for task in db.scalars(select(Task).where(Task.booking_id == booking.id,
                                                  Task.title.ilike("%booking form%"))).all():
            task.completed = True
        workflow = dict(booking.workflow_state or {})
        workflow.pop("booking_form_review", None)
        booking.workflow_state = workflow
        booking_form_review = db.scalar(select(Task).where(
            Task.booking_id == booking.id,
            Task.workflow_key == "wbm_review_booking_form",
        ).limit(1))
        if booking_form_review:
            booking_form_review.completed = False
        else:
            db.add(Task(
                booking_id=booking.id,
                title="Review submitted Wedding Booking Form",
                workflow_key="wbm_review_booking_form",
            ))
    elif payload.form_type == FINAL_TIMINGS_FORM_TYPE:
        workflow = dict(booking.workflow_state or {})
        workflow.pop("final_timings_review", None)
        booking.workflow_state = workflow
        review_task = db.scalar(select(Task).where(
            Task.booking_id == booking.id,
            Task.workflow_key == "wbm_review_final_timings",
        ).limit(1))
        if review_task:
            review_task.completed = False
        else:
            db.add(Task(
                booking_id=booking.id,
                title="Review final wedding timings",
                workflow_key="wbm_review_final_timings",
            ))
        db.flush()
        final_document, _ = ensure_final_timings_document(db, booking, row)
    audit(db, "submit_form", "booking", booking.id, {
        "form_type": payload.form_type,
        "pdf_document_id": final_document.id if final_document else None,
    })
    db.commit()
    if payload.form_type == "booking_form":
        sync_booking_calendar_safely(db, booking)
    return {"ok": True, "submitted_at": row.submitted_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "pdf_document_id": final_document.id if final_document else None}


@app.get("/api/bookings/{booking_id}/final-timings.pdf")
def download_final_timings_pdf(
    booking_id: str,
    inline: bool = Query(False),
    _: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(
        Booking.id == booking_id
    ))
    if not booking:
        raise HTTPException(404, "Record not found")
    submission = db.scalar(select(FormSubmission).where(
        FormSubmission.booking_id == booking.id,
        FormSubmission.form_type == FINAL_TIMINGS_FORM_TYPE,
    ).limit(1))
    if not submission:
        raise HTTPException(409, "The couple has not submitted their Final Wedding Timings Form")
    document, content = ensure_final_timings_document(db, booking, submission)
    db.commit()
    disposition = "inline" if inline else "attachment"
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'{disposition}; filename="{document.original_name}"',
    })


@app.post("/api/bookings/{booking_id}/booking-form/review")
def review_booking_form(
    booking_id: str,
    admin: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Record not found")
    submission = db.scalar(select(FormSubmission).where(
        FormSubmission.booking_id == booking.id,
        FormSubmission.form_type == "booking_form",
    ).limit(1))
    if not submission:
        raise HTTPException(409, "The couple has not submitted their Wedding Booking Form")
    reviewed_at = datetime.now(timezone.utc)
    workflow = dict(booking.workflow_state or {})
    workflow["booking_form_review"] = {
        "reviewed_at": reviewed_at.isoformat(),
        "reviewed_by": admin.email,
        "submission_updated_at": submission.updated_at.isoformat(),
    }
    booking.workflow_state = workflow
    for task in db.scalars(select(Task).where(
        Task.booking_id == booking.id,
        Task.workflow_key == "wbm_review_booking_form",
    )).all():
        task.completed = True
    audit(db, "review_booking_form", "booking", booking.id, {
        "admin": admin.email,
        "submission_id": submission.id,
    })
    db.commit()
    return {"ok": True, "reviewed_at": reviewed_at.isoformat(),
            "reviewed_by": admin.email}


@app.post("/api/bookings/{booking_id}/final-timings/review")
def review_final_timings(
    booking_id: str,
    admin: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Record not found")
    submission = db.scalar(select(FormSubmission).where(
        FormSubmission.booking_id == booking.id,
        FormSubmission.form_type == FINAL_TIMINGS_FORM_TYPE,
    ).limit(1))
    if not submission:
        raise HTTPException(409, "The couple has not submitted their Final Wedding Timings Form")
    reviewed_at = datetime.now(timezone.utc)
    workflow = dict(booking.workflow_state or {})
    workflow["final_timings_review"] = {
        "reviewed_at": reviewed_at.isoformat(),
        "reviewed_by": admin.email,
        "submission_updated_at": submission.updated_at.isoformat(),
    }
    booking.workflow_state = workflow
    for task in db.scalars(select(Task).where(
        Task.booking_id == booking.id,
        Task.workflow_key == "wbm_review_final_timings",
    )).all():
        task.completed = True
    audit(db, "review_final_timings", "booking", booking.id, {
        "admin": admin.email,
        "submission_id": submission.id,
    })
    db.commit()
    return {"ok": True, "reviewed_at": reviewed_at.isoformat(), "reviewed_by": admin.email}


@app.post("/api/client/{token}/contract")
def accept_contract(token: str, payload: ContractAcceptIn, request: Request, db: Session = Depends(get_db)):
    if not payload.agreed:
        raise HTTPException(422, "You must agree before accepting the contract")
    portal = resolve_portal(db, token)
    booking = portal.booking
    require_booking_journey_unlocked(db, booking)
    if booking.legacy_source == "studio_ninja":
        raise HTTPException(409, "This original Studio Ninja agreement remains protected and unchanged")
    if payload.accepted_email.lower() != booking.client.email.lower():
        raise HTTPException(422, "Please use the email address shown on your booking")
    if db.scalar(select(ContractAcceptance).where(ContractAcceptance.booking_id == booking.id)):
        raise HTTPException(409, "This agreement has already been accepted")
    contract = db.scalar(select(ContractTemplate).where(ContractTemplate.brand == booking.brand,
                                                        ContractTemplate.is_active.is_(True)))
    if not contract:
        raise HTTPException(404, "No active agreement is available")
    signed_at = datetime.now(timezone.utc)
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    row = ContractAcceptance(booking_id=booking.id, contract_title=contract.title,
                             contract_version=contract.version, contract_body=contract.body,
                             accepted_name=payload.accepted_name.strip(),
                             accepted_email=str(payload.accepted_email).lower(),
                             ip_address=forwarded or (request.client.host if request.client else None),
                             user_agent=request.headers.get("user-agent", "")[:500],
                             acceptance_source="client_portal", is_legacy_import=False,
                             accepted_at=signed_at,
                             supplier_signed_name="Mark Adam Powell",
                             supplier_signed_at=signed_at,
                             supplier_signature_method="automatic_after_client_acceptance")
    db.add(row)
    db.flush()
    for task in db.scalars(select(Task).where(Task.booking_id == booking.id,
                                              Task.title.ilike("%contract%"))).all():
        task.completed = True
    completion_email_sent, completion_email_error = send_contract_completion_email(db, booking)
    audit(db, "accept_contract", "booking", booking.id,
          {"version": contract.version, "accepted_name": row.accepted_name,
           "supplier_signed_name": row.supplier_signed_name,
           "completion_email_sent": completion_email_sent})
    db.commit()
    return {"ok": True, "accepted_at": row.accepted_at.isoformat(),
            "supplier_signed_name": row.supplier_signed_name,
            "supplier_signed_at": row.supplier_signed_at.isoformat(),
            "completion_email_sent": completion_email_sent,
            "completion_email_error": completion_email_error}


def send_contract_completion_email(db: Session, booking: Booking) -> tuple[bool, str | None]:
    """Notify the client after both parties are recorded without touching legacy imports."""
    recipient = client_email_recipient(db, booking)
    template = db.scalar(select(EmailTemplate).where(
        EmailTemplate.brand == booking.brand,
        EmailTemplate.template_key == "contract_completed",
        EmailTemplate.is_active.is_(True),
    ))
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
    error = None
    if not automations_allowed(booking):
        error = "Automatic client email is paused for this imported booking"
    elif not template:
        error = "The signed-agreement email template is missing or inactive"
    elif not profile:
        error = "The business profile is missing"
    elif not smtp_ready(booking.brand):
        error = f"SMTP is not configured for {booking.brand.value}"
    if error:
        db.add(EmailLog(booking_id=booking.id, template_key="contract_completed",
                        recipient=recipient,
                        subject=(template.subject if template else "Agreement signed by both parties"),
                        status="failed", error=error))
        return False, error
    portal_url = issue_client_email_url(db, booking, "contract_completed")
    try:
        subject, email_body = send_booking_template_email(
            db, booking, profile, template, portal_url
        )
        db.add(EmailLog(booking_id=booking.id, template_key="contract_completed",
                        recipient=recipient, subject=subject, body=email_body, status="sent"))
        return True, None
    except Exception as exc:
        error = str(exc)
        db.add(EmailLog(booking_id=booking.id, template_key="contract_completed",
                        recipient=recipient, subject=template.subject,
                        status="failed", error=error[:2000]))
        return False, error


@app.post("/api/bookings/{booking_id}/contract/countersign")
def countersign_existing_contract(booking_id: str, _: Admin = Depends(current_admin),
                                  db: Session = Depends(get_db)):
    booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(Booking.id == booking_id))
    if not booking:
        raise HTTPException(404, "Booking not found")
    acceptance = db.scalar(select(ContractAcceptance).where(
        ContractAcceptance.booking_id == booking.id
    ))
    if not acceptance:
        raise HTTPException(409, "The client has not accepted the agreement yet")
    if acceptance.is_legacy_import or booking.legacy_source == "studio_ninja":
        raise HTTPException(409, "Imported Studio Ninja agreements remain protected and unchanged")
    if acceptance.supplier_signed_at:
        raise HTTPException(409, "This agreement has already been countersigned")
    acceptance.supplier_signed_name = "Mark Adam Powell"
    acceptance.supplier_signed_at = datetime.now(timezone.utc)
    acceptance.supplier_signature_method = "admin_authorised_existing_acceptance"
    completion_email_sent, completion_email_error = send_contract_completion_email(db, booking)
    audit(db, "countersign_contract", "booking", booking.id,
          {"supplier_signed_name": acceptance.supplier_signed_name,
           "completion_email_sent": completion_email_sent})
    db.commit()
    return {"ok": True, "contract": contract_acceptance_json(acceptance),
            "completion_email_sent": completion_email_sent,
            "completion_email_error": completion_email_error}


@app.post("/api/bookings/{booking_id}/contract/completion-email")
def resend_contract_completion_email(booking_id: str, _: Admin = Depends(current_admin),
                                     db: Session = Depends(get_db)):
    booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(
        Booking.id == booking_id
    ))
    if not booking:
        raise HTTPException(404, "Booking not found")
    acceptance = db.scalar(select(ContractAcceptance).where(
        ContractAcceptance.booking_id == booking.id
    ))
    if not acceptance or not acceptance.supplier_signed_at:
        raise HTTPException(409, "The agreement must be signed by both parties first")
    if acceptance.is_legacy_import or booking.legacy_source == "studio_ninja":
        raise HTTPException(409, "Imported Studio Ninja agreements remain protected and unchanged")
    sent, error = send_contract_completion_email(db, booking)
    audit(db, "send_contract_completion_email", "booking", booking.id,
          {"sent": sent, "error": error})
    db.commit()
    if not sent:
        raise HTTPException(503, error or "The signed-agreement email could not be sent")
    return {"ok": True, "completion_email_sent": True}


def contract_for_booking(db: Session, booking_id: str) -> tuple[ContractAcceptance, BusinessProfile]:
    acceptance = db.scalar(select(ContractAcceptance).where(
        ContractAcceptance.booking_id == booking_id
    ))
    if not acceptance:
        raise HTTPException(404, "No accepted agreement is available for this booking")
    booking = db.get(Booking, booking_id)
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
    if not profile:
        raise HTTPException(404, "Business profile not found")
    return acceptance, profile


@app.get("/api/bookings/{booking_id}/contract.pdf")
def admin_contract_pdf(booking_id: str, inline: bool = Query(False),
                       _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    acceptance, profile = contract_for_booking(db, booking_id)
    return Response(contract_acceptance_pdf(acceptance, profile), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'{"inline" if inline else "attachment"}; filename="signed-agreement.pdf"'})


@app.get("/api/client/{token}/contract.pdf")
def public_contract_pdf(token: str, inline: bool = Query(False), db: Session = Depends(get_db)):
    portal = resolve_portal(db, token)
    acceptance, profile = contract_for_booking(db, portal.booking_id)
    return Response(contract_acceptance_pdf(acceptance, profile), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'{"inline" if inline else "attachment"}; filename="signed-agreement.pdf"'})


def run_due_reminders(db: Session) -> dict:
    today = date.today()
    sent, skipped, failed = 0, 0, 0
    bookings = db.scalars(select(Booking).options(selectinload(Booking.client),
                                                  selectinload(Booking.invoices),
                                                  selectinload(Booking.quotes))
                          .where(Booking.archived_at.is_(None), Booking.status != RecordStatus.CANCELLED)).all()
    for booking in bookings:
        reminders: list[tuple[str, str, str | None, int]] = []
        is_studio_ninja = booking.legacy_source == "studio_ninja"
        if is_studio_ninja:
            # Hard safety boundary: this is the sole automatic communication
            # ever permitted for a Studio Ninja import. Do not add the normal
            # reminder workflow to this branch.
            if not studio_ninja_final_timings_email_due(booking, today):
                continue
            reminders.append(("check_in_30", "check_in_30", "timings", 365))
        elif not automations_allowed(booking):
            continue
        has_balance = any(invoice.status not in ("void", "cancelled") and invoice.paid < invoice.total
                          for invoice in booking.invoices)
        is_wbm_wedding = booking.brand == Brand.WBM and booking.kind == RecordKind.WEDDING
        accepted_quote = next((quote for quote in booking.quotes if quote.status == "accepted"), None)

        # Quote chasing is based on the most recent successfully sent initial quote.
        # It stops immediately when a package has been accepted.
        if (not is_studio_ninja and is_wbm_wedding and not accepted_quote
                and booking.status in (RecordStatus.ENQUIRY, RecordStatus.QUOTED)):
            quote_sent_at = db.scalar(select(EmailLog.sent_at).where(
                EmailLog.booking_id == booking.id,
                EmailLog.template_key == "quote",
                EmailLog.status == "sent",
            ).order_by(EmailLog.sent_at.desc()).limit(1))
            if quote_sent_at:
                days_since_quote = (today - quote_sent_at.date()).days
                if days_since_quote == 1:
                    reminders.append(("quote_followup_1", "quote_followup_1", "quote", 365))
                if days_since_quote == 9:
                    reminders.append(("quote_followup_final", "quote_followup_final", "quote", 365))

        if not is_studio_ninja and is_wbm_wedding and accepted_quote:
            accepted_invoice = next(
                (invoice for invoice in booking.invoices if invoice.id == accepted_quote.invoice_id),
                None,
            )
            if (accepted_invoice and accepted_invoice.status not in ("void", "cancelled")
                    and money(accepted_invoice.paid) <= 0
                    and accepted_invoice.deposit_due_date == today):
                reminders.append(("deposit_due_1", "deposit_due_1", "invoices", 365))

        if not is_studio_ninja and is_wbm_wedding and booking.event_date and booking.status in (
                RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS):
            days_to_wedding = (booking.event_date - today).days
            if days_to_wedding == 120:
                reminders.append(("check_in_120", "check_in_120", None, 0))
            if days_to_wedding == 30:
                reminders.append(("check_in_30", "check_in_30", "timings", 365))

        if not is_studio_ninja and is_wbm_wedding and booking.balance_due_date and has_balance:
            days_to_balance = (booking.balance_due_date - today).days
            if days_to_balance == 7:
                reminders.append(("balance_due_7", "balance_due_7", "invoices", 365))
            if days_to_balance == 1:
                reminders.append(("balance_due_1", "balance_due_1", "invoices", 365))
            overdue_days = -days_to_balance
            if overdue_days >= 2 and overdue_days % 2 == 0:
                reminders.append((f"balance_overdue_{overdue_days}", "balance_overdue_2", "invoices", 365))

        for reminder_key, template_key, portal_tab, expires_days in reminders:
            if db.scalar(select(ReminderLog).where(ReminderLog.booking_id == booking.id,
                                                   ReminderLog.reminder_key == reminder_key,
                                                   ReminderLog.scheduled_for == today)):
                skipped += 1
                continue
            reminder = ReminderLog(booking_id=booking.id, reminder_key=reminder_key, scheduled_for=today)
            db.add(reminder)
            template = db.scalar(select(EmailTemplate).where(EmailTemplate.brand == booking.brand,
                                                             EmailTemplate.template_key == template_key,
                                                             EmailTemplate.is_active.is_(True)))
            profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
            try:
                if not template:
                    raise RuntimeError("Reminder template is inactive or missing")
                portal_url = issue_client_email_url(
                    db, booking, template_key, max(365, expires_days)
                )
                recipient = client_email_recipient(db, booking)
                subject, email_body = send_booking_template_email(
                    db, booking, profile, template, portal_url
                )
                reminder.status, reminder.sent_at = "sent", datetime.now(timezone.utc)
                db.add(EmailLog(booking_id=booking.id, template_key=template_key, recipient=recipient,
                                subject=subject, body=email_body, status="sent"))
                sent += 1
            except Exception as exc:
                reminder.status, reminder.error = "failed", str(exc)[:2000]
                failed += 1
            db.commit()
    return {"sent": sent, "skipped": skipped, "failed": failed}


@app.post("/api/communications/reminders/run")
def run_reminders_now(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if not smtp_ready():
        raise HTTPException(503, "SMTP is not configured")
    return run_due_reminders(db)


async def reminder_loop():
    while True:
        await asyncio.sleep(max(1, settings.reminder_scan_hours) * 3600)
        if settings.reminders_enabled and smtp_ready():
            with SessionLocal() as db:
                await asyncio.to_thread(run_due_reminders, db)


register_v82_routes(app)
register_v84_routes(app)
register_google_calendar_routes(app)
register_mail_routes(app)
register_legacy_import_routes(app)
register_legacy_archive_import_routes(app)
register_accounts_integration_routes(app)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/client/{token}", include_in_schema=False)
def client_portal_page(token: str):
    return FileResponse(STATIC_DIR / "client.html")


@app.get("/enquiry", include_in_schema=False)
def public_enquiry_page():
    return FileResponse(STATIC_DIR / "enquiry.html")


@app.get("/bookings/{booking_id}/{section}", include_in_schema=False)
def admin_booking_page(booking_id: str, section: str):
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/bookings/{booking_id}", include_in_schema=False)
def admin_booking_overview_page(booking_id: str):
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{view}", include_in_schema=False)
def admin_workspace_page(view: str):
    allowed = {
        "dashboard", "enquiries", "weddings", "projects", "calendar",
        "workflows", "mail", "invoices", "documents", "forms",
        "bookingforms", "packages", "communications", "settings",
    }
    if view not in allowed:
        raise HTTPException(404, "Page not found")
    return FileResponse(STATIC_DIR / "index.html")

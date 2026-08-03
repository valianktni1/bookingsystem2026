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
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .bootstrap import bootstrap
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .email_service import send_template_email, smtp_ready
from .migrations import apply_safe_migrations
from .models import (AddOnOption, Admin, AuditLog, Booking, BookingNote, Brand, BusinessProfile,
                     Client, ClientPortalToken, ContractAcceptance, ContractTemplate, Document,
                     EmailLog, EmailTemplate, FormSubmission, Invoice, PackageOption, Payment,
                     Quote, RecordKind, RecordStatus, ReminderLog, Task)
from .pdf import invoice_pdf
from .schemas import (AddOnOptionIn, AddOnOptionPatch, BookingIn, BookingPatch, BusinessPatch,
                      ContractAcceptIn, ContractTemplatePatch, EmailTemplatePatch, EnquiryIn, InvoiceIn,
                      LoginIn, NoteIn, PackageOptionIn, PackageOptionPatch, PaymentIn, PortalCreateIn,
                      PublicFormIn, QuoteAcceptIn, SendEmailIn, TaskIn, TaskPatch)
from .security import create_token, current_admin, verify_password
from .services import audit, create_default_tasks, dashboard_counts, invoice_status, next_invoice_number

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
    yield
    reminder_task.cancel()
    with suppress(asyncio.CancelledError):
        await reminder_task


app = FastAPI(title=settings.app_name, version="2.1.0-phase2b", lifespan=lifespan, docs_url=None, redoc_url=None)


def money(value) -> float:
    return float(value or 0)


def confirm_when_paid(booking: Booking) -> bool:
    """Confirm an enquiry or quote after a dated payment has been recorded."""
    if (booking.status in (RecordStatus.ENQUIRY, RecordStatus.QUOTED)
            and money(booking.deposit_amount) > 0 and booking.deposit_paid_date):
        booking.status = RecordStatus.CONFIRMED
        return True
    return False


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
            "created_at": item.created_at.isoformat()}


def invoice_json(item: Invoice) -> dict:
    return {"id": item.id, "booking_id": item.booking_id, "brand": item.brand.value,
            "sequence": item.sequence, "number": item.number, "issue_date": item.issue_date.isoformat(),
            "supply_date": item.supply_date.isoformat() if item.supply_date else None,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "description": item.description, "notes": item.notes, "total": money(item.total),
            "line_items": item.line_items or [],
            "paid": money(item.paid), "balance": money(item.total - item.paid), "status": item.status,
            "client": item.booking.title if item.booking else None,
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
            "display_order": item.display_order, "is_active": item.is_active}


def quote_json(item: Quote | None) -> dict | None:
    if not item:
        return None
    return {"id": item.id, "status": item.status, "package_id": item.package_id,
            "selected_addon_ids": item.selected_addon_ids or [], "line_items": item.line_items or [],
            "total": money(item.total), "deposit_amount": money(item.deposit_amount),
            "invoice_id": item.invoice_id,
            "accepted_at": item.accepted_at.isoformat() if item.accepted_at else None}


def document_json(item: Document) -> dict:
    return {"id": item.id, "booking_id": item.booking_id,
            "booking_title": item.booking.title if item.booking else None, "brand": item.booking.brand.value if item.booking else None,
            "category": item.category, "original_name": item.original_name, "content_type": item.content_type,
            "size_bytes": item.size_bytes, "created_at": item.created_at.isoformat()}


def booking_json(item: Booking, full: bool = False, activity: list[AuditLog] | None = None) -> dict:
    data = {"id": item.id, "brand": item.brand.value, "kind": item.kind.value, "status": item.status.value,
            "title": item.title, "event_date": item.event_date.isoformat() if item.event_date else None,
            "venue_or_project": item.venue_or_project, "package_name": item.package_name,
            "quoted_total": money(item.quoted_total), "deposit_amount": money(item.deposit_amount),
            "deposit_paid_date": item.deposit_paid_date.isoformat() if item.deposit_paid_date else None,
            "balance_due_date": item.balance_due_date.isoformat() if item.balance_due_date else None,
            "client": client_json(item.client), "archived": item.archived_at is not None,
            "archived_at": item.archived_at.isoformat() if item.archived_at else None,
            "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat()}
    if full:
        data.update({"notes": item.notes, "form_data": item.form_data, "workflow_state": item.workflow_state,
                     "tasks": [task_json(t) for t in sorted(item.tasks, key=lambda x: (x.completed, x.created_at))],
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
        selectinload(Booking.documents), selectinload(Booking.booking_notes)
    ).where(Booking.id == booking_id))
    if not item:
        raise HTTPException(404, "Record not found")
    return item


@app.get("/api/health")
def health():
    return {"status": "ok", "phase": "2B", "smtp_configured": smtp_ready(),
            "reminders_enabled": settings.reminders_enabled}


@app.get("/api/public/catalog")
def public_catalog(db: Session = Depends(get_db)):
    packages = db.scalars(select(PackageOption).where(PackageOption.brand == Brand.WBM,
                                                       PackageOption.is_active.is_(True))
                          .order_by(PackageOption.display_order, PackageOption.price)).all()
    return {"packages": [package_json(x) for x in packages]}


@app.post("/api/public/enquiries", status_code=201)
def create_public_enquiry(payload: EnquiryIn, request: Request, db: Session = Depends(get_db)):
    if payload.website:
        return {"ok": True}
    if not payload.privacy_agreed:
        raise HTTPException(422, "Please agree to the privacy notice before submitting")
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
    form_data = payload.model_dump(exclude={"website", "privacy_agreed"}, mode="json")
    title = f"{payload.primary_first_name.strip()} & {payload.partner_first_name.strip()}"
    booking = Booking(brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.ENQUIRY,
                      title=title, client_id=client.id, event_date=payload.event_date,
                      venue_or_project=payload.location.strip(), package_name=payload.package_interest,
                      notes=payload.message.strip() if payload.message else None,
                      form_data={"website_enquiry": form_data},
                      workflow_state={"source": "website_enquiry", "received_at": datetime.now(timezone.utc).isoformat()})
    db.add(booking)
    db.flush()
    create_default_tasks(db, booking.id, booking.kind)
    audit(db, "website_enquiry", "booking", booking.id,
          {"title": title, "event_date": payload.event_date.isoformat(),
           "heard_about_us": payload.heard_about_us})

    template = db.scalar(select(EmailTemplate).where(EmailTemplate.brand == Brand.WBM,
                                                     EmailTemplate.template_key == "enquiry_received",
                                                     EmailTemplate.is_active.is_(True)))
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == Brand.WBM))
    if template and profile and smtp_ready(Brand.WBM):
        try:
            subject, _ = send_template_email(booking, profile, template)
            db.add(EmailLog(booking_id=booking.id, template_key=template.template_key,
                            recipient=client.email, subject=subject, status="sent"))
        except Exception as exc:
            db.add(EmailLog(booking_id=booking.id, template_key=template.template_key,
                            recipient=client.email, subject=template.subject,
                            status="failed", error=str(exc)[:2000]))
    db.commit()
    return {"ok": True, "message": "Thank you - your enquiry has been received."}


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


@app.get("/api/dashboard")
def dashboard(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    counts = dashboard_counts(db)
    upcoming = db.scalars(select(Booking).options(selectinload(Booking.client))
                          .where(Booking.archived_at.is_(None), Booking.event_date >= date.today())
                          .order_by(Booking.event_date).limit(8)).all()
    tasks = db.scalars(select(Task).options(selectinload(Task.booking))
                       .join(Booking).where(Task.completed.is_(False), Booking.archived_at.is_(None))
                       .order_by(Task.due_at.asc().nullslast()).limit(10)).all()
    counts.update({"upcoming": [booking_json(x) for x in upcoming], "tasks": [task_json(t) for t in tasks]})
    return counts


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
    create_default_tasks(db, booking.id, booking.kind)
    audit(db, "create", "booking", booking.id, {"title": booking.title, "brand": booking.brand.value})
    db.commit()
    return get_booking(booking.id, _, db)


@app.get("/api/bookings/{booking_id}")
def get_booking(booking_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = full_booking(db, booking_id)
    activity = db.scalars(select(AuditLog).where(AuditLog.entity_id == booking_id)
                          .order_by(AuditLog.created_at.desc()).limit(50)).all()
    return booking_json(item, full=True, activity=activity)


@app.patch("/api/bookings/{booking_id}")
def patch_booking(booking_id: str, payload: BookingPatch, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = db.get(Booking, booking_id)
    if not item:
        raise HTTPException(404, "Record not found")
    values = payload.model_dump(exclude_unset=True)
    client_values = values.pop("client", None)
    for key, value in values.items():
        setattr(item, key, value)
    if client_values:
        client = db.get(Client, item.client_id)
        for key, value in client_values.items():
            setattr(client, key, value)
    auto_confirmed = confirm_when_paid(item)
    audit(db, "update", "booking", item.id,
          {"fields": list(payload.model_fields_set), "auto_confirmed": auto_confirmed})
    db.commit()
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
    stmt = select(Task).options(selectinload(Task.booking)).join(Booking).where(Booking.archived_at.is_(None))
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
def list_invoices(brand: Brand | None = None, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(Invoice).options(selectinload(Invoice.booking), selectinload(Invoice.payments)).order_by(Invoice.sequence.desc())
    if brand:
        stmt = stmt.where(Invoice.brand == brand)
    return [invoice_json(x) for x in db.scalars(stmt).all()]


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


@app.post("/api/invoices/{invoice_id}/payments", status_code=201)
def create_payment(invoice_id: str, payload: PaymentIn, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    invoice = full_invoice(db, invoice_id)
    if payload.amount > invoice.total - invoice.paid:
        raise HTTPException(422, "Payment cannot exceed the outstanding balance")
    payment = Payment(invoice_id=invoice.id, **payload.model_dump())
    db.add(payment)
    invoice.paid += payload.amount
    invoice.status = invoice_status(invoice.total, invoice.paid)
    if invoice.booking and not invoice.booking.deposit_paid_date:
        invoice.booking.deposit_paid_date = payload.paid_date
    if invoice.booking:
        invoice.booking.deposit_amount = max(invoice.booking.deposit_amount or Decimal("0"), payload.amount)
        auto_confirmed = confirm_when_paid(invoice.booking)
    else:
        auto_confirmed = False
    audit(db, "record_payment", "booking", invoice.booking_id,
          {"invoice": invoice.number, "amount": money(payload.amount), "auto_confirmed": auto_confirmed})
    db.commit()
    return invoice_json(full_invoice(db, invoice.id))


@app.delete("/api/payments/{payment_id}", status_code=204)
def delete_payment(payment_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    invoice = db.get(Invoice, payment.invoice_id)
    invoice.paid = max(Decimal("0"), invoice.paid - payment.amount)
    invoice.status = invoice_status(invoice.total, invoice.paid)
    db.delete(payment)
    audit(db, "delete_payment", "booking", invoice.booking_id, {"invoice": invoice.number})
    db.commit()


@app.get("/api/invoices/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    invoice = full_invoice(db, invoice_id)
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == invoice.brand))
    return Response(invoice_pdf(invoice, profile), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{invoice.number}.pdf"'})


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
def upload_document(booking_id: str, category: str = Query(pattern="^[a-zA-Z0-9_-]{2,30}$"),
                    file: UploadFile = File(...), _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
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
                        storage_name=storage_name, content_type=content_type, size_bytes=size)
    db.add(document)
    db.flush()
    audit(db, "upload_document", "booking", booking_id, {"name": original, "category": category})
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


def issue_portal_token(db: Session, booking_id: str, expires_days: int = 90) -> tuple[str, ClientPortalToken]:
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
        raise HTTPException(404, "This private link is invalid or has expired")
    return row


def portal_status_json(db: Session, booking: Booking) -> dict:
    submissions = db.scalars(select(FormSubmission).where(FormSubmission.booking_id == booking.id)).all()
    acceptance = db.scalar(select(ContractAcceptance).where(ContractAcceptance.booking_id == booking.id))
    logs = db.scalars(select(EmailLog).where(EmailLog.booking_id == booking.id)
                      .order_by(EmailLog.sent_at.desc()).limit(20)).all()
    quote = db.scalar(select(Quote).where(Quote.booking_id == booking.id)
                      .order_by(Quote.created_at.desc()).limit(1))
    quote_data = quote_json(quote)
    if quote_data and quote.invoice_id:
        invoice = db.get(Invoice, quote.invoice_id)
        quote_data["invoice_number"] = invoice.number if invoice else None
    return {
        "submissions": [{"id": x.id, "form_type": x.form_type, "data": x.data,
                         "submitted_at": x.submitted_at.isoformat()} for x in submissions],
        "contract": ({"accepted_name": acceptance.accepted_name, "accepted_email": acceptance.accepted_email,
                      "accepted_at": acceptance.accepted_at.isoformat(), "version": acceptance.contract_version}
                     if acceptance else None),
        "emails": [{"template_key": x.template_key, "recipient": x.recipient, "subject": x.subject,
                    "status": x.status, "sent_at": x.sent_at.isoformat()} for x in logs],
        "quote": quote_data,
    }


@app.get("/api/communications/templates")
def list_templates(brand: Brand | None = None, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(EmailTemplate).order_by(EmailTemplate.brand, EmailTemplate.display_name)
    if brand:
        stmt = stmt.where(EmailTemplate.brand == brand)
    rows = db.scalars(stmt).all()
    contracts = db.scalars(select(ContractTemplate).order_by(ContractTemplate.brand)).all()
    return {"smtp_configured": smtp_ready(), "reminders_enabled": settings.reminders_enabled,
            "templates": [{"id": x.id, "brand": x.brand.value, "template_key": x.template_key,
                           "display_name": x.display_name, "subject": x.subject, "body": x.body,
                           "is_active": x.is_active} for x in rows],
            "contracts": [{"id": x.id, "brand": x.brand.value, "title": x.title, "version": x.version,
                           "body": x.body, "is_active": x.is_active} for x in contracts]}


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
    raw, row = issue_portal_token(db, booking_id, payload.expires_days)
    audit(db, "create_client_link", "booking", booking_id, {"expires_at": row.expires_at.isoformat()})
    db.commit()
    return {"url": f"{settings.app_url.rstrip('/')}/client/{raw}", "expires_at": row.expires_at.isoformat()}


@app.post("/api/bookings/{booking_id}/emails/send")
def send_booking_email(booking_id: str, payload: SendEmailIn, _: Admin = Depends(current_admin),
                       db: Session = Depends(get_db)):
    booking = db.scalar(select(Booking).options(selectinload(Booking.client)).where(Booking.id == booking_id))
    if not booking:
        raise HTTPException(404, "Record not found")
    template = db.scalar(select(EmailTemplate).where(EmailTemplate.brand == booking.brand,
                                                     EmailTemplate.template_key == payload.template_key,
                                                     EmailTemplate.is_active.is_(True)))
    if not template:
        raise HTTPException(404, "Active email template not found")
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
    try:
        subject, _ = send_template_email(booking, profile, template, payload.portal_url)
        log = EmailLog(booking_id=booking.id, template_key=template.template_key,
                       recipient=booking.client.email, subject=subject, status="sent")
        db.add(log)
        audit(db, "send_email", "booking", booking.id, {"template": template.template_key})
        db.commit()
        return {"ok": True, "subject": subject}
    except Exception as exc:
        db.add(EmailLog(booking_id=booking.id, template_key=template.template_key,
                        recipient=booking.client.email, subject=template.subject,
                        status="failed", error=str(exc)[:2000]))
        db.commit()
        raise HTTPException(503, str(exc))


@app.get("/api/client/{token}")
def public_portal_data(token: str, db: Session = Depends(get_db)):
    portal = resolve_portal(db, token)
    booking = portal.booking
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
    contract = db.scalar(select(ContractTemplate).where(ContractTemplate.brand == booking.brand,
                                                        ContractTemplate.is_active.is_(True)))
    status_data = portal_status_json(db, booking)
    packages = db.scalars(select(PackageOption).where(PackageOption.brand == booking.brand,
                                                       PackageOption.is_active.is_(True))
                          .order_by(PackageOption.display_order, PackageOption.price)).all()
    addons = db.scalars(select(AddOnOption).where(AddOnOption.brand == booking.brand,
                                                  AddOnOption.is_active.is_(True))
                        .order_by(AddOnOption.display_order, AddOnOption.price)).all()
    return {"business": {"name": profile.display_name, "email": profile.email, "phone": profile.phone},
            "record": {"title": booking.title, "kind": booking.kind.value,
                       "event_date": booking.event_date.isoformat() if booking.event_date else None,
                       "venue_or_project": booking.venue_or_project, "package_name": booking.package_name,
                       "quoted_total": money(booking.quoted_total), "deposit_amount": money(booking.deposit_amount),
                       "client": client_json(booking.client)},
            "contract_template": ({"title": contract.title, "version": contract.version, "body": contract.body}
                                  if contract else None),
            "catalog": {"packages": [package_json(x) for x in packages],
                        "addons": [addon_json(x) for x in addons]}, **status_data}


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
    requested_ids = list(dict.fromkeys(payload.addon_ids))
    addons = db.scalars(select(AddOnOption).where(AddOnOption.id.in_(requested_ids),
                                                  AddOnOption.brand == booking.brand,
                                                  AddOnOption.is_active.is_(True))).all() if requested_ids else []
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
    for addon in addons:
        line_items.append({"type": "addon", "code": addon.code, "name": addon.name,
                           "description": addon.description, "quantity": 1,
                           "unit_price": money(addon.price), "total": money(addon.price)})
    total = package.price + sum((x.price for x in addons), Decimal("0"))
    quote = Quote(booking_id=booking.id, status="accepted", package_id=package.id,
                  selected_addon_ids=requested_ids, line_items=line_items, total=total,
                  deposit_amount=package.deposit_amount, accepted_at=datetime.now(timezone.utc))
    db.add(quote)
    db.flush()
    sequence, number = next_invoice_number(db, booking.brand)
    invoice = Invoice(booking_id=booking.id, brand=booking.brand, sequence=sequence, number=number,
                      issue_date=date.today(), supply_date=booking.event_date,
                      due_date=booking.balance_due_date, description=package.name, total=total,
                      paid=Decimal("0"), status="unpaid", line_items=line_items,
                      notes=f"Booking fee of £{money(package.deposit_amount):,.2f} is due by bank transfer.")
    db.add(invoice)
    db.flush()
    quote.invoice_id = invoice.id
    booking.package_name = package.name
    booking.quoted_total = total
    booking.deposit_amount = package.deposit_amount
    if booking.status == RecordStatus.ENQUIRY:
        booking.status = RecordStatus.QUOTED
    for task in db.scalars(select(Task).where(Task.booking_id == booking.id,
                                              Task.title.ilike("%quote%"))).all():
        task.completed = True
    audit(db, "accept_quote", "booking", booking.id,
          {"package": package.name, "addons": [x.name for x in addons],
           "total": money(total), "invoice": number})
    db.commit()
    return {"ok": True, "quote": quote_json(quote), "invoice": invoice_json(invoice)}


@app.post("/api/client/{token}/forms")
def submit_public_form(token: str, payload: PublicFormIn, db: Session = Depends(get_db)):
    portal = resolve_portal(db, token)
    booking = portal.booking
    row = db.scalar(select(FormSubmission).where(FormSubmission.booking_id == booking.id,
                                                 FormSubmission.form_type == payload.form_type))
    if row:
        row.data = payload.data
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = FormSubmission(booking_id=booking.id, form_type=payload.form_type, data=payload.data)
        db.add(row)
    if payload.form_type == "booking_form":
        booking.form_data = payload.data
        if payload.data.get("primary_phone"):
            booking.client.phone = str(payload.data["primary_phone"]).strip()
        if payload.data.get("partner_full_name"):
            booking.client.partner_name = str(payload.data["partner_full_name"]).strip()
        address_parts = [payload.data.get(key) for key in ("street_address", "town", "county", "postcode")]
        address = ", ".join(str(value).strip() for value in address_parts if value)
        if address:
            booking.client.address = address
        if payload.data.get("wedding_date"):
            try:
                booking.event_date = date.fromisoformat(str(payload.data["wedding_date"]))
            except ValueError:
                pass
        if payload.data.get("ceremony_details") and not booking.venue_or_project:
            booking.venue_or_project = str(payload.data["ceremony_details"]).strip()[:240]
        accepted_quote = db.scalar(select(Quote).where(Quote.booking_id == booking.id,
                                                        Quote.status == "accepted"))
        if payload.data.get("package_selected") and not accepted_quote:
            booking.package_name = str(payload.data["package_selected"]).strip()[:160]
        for task in db.scalars(select(Task).where(Task.booking_id == booking.id,
                                                  Task.title.ilike("%booking form%"))).all():
            task.completed = True
    else:
        booking.workflow_state = {**(booking.workflow_state or {}), "final_questionnaire": payload.data}
        for task in db.scalars(select(Task).where(Task.booking_id == booking.id,
                                                  Task.title.ilike("%questionnaire%"))).all():
            task.completed = True
    audit(db, "submit_form", "booking", booking.id, {"form_type": payload.form_type})
    db.commit()
    return {"ok": True, "submitted_at": row.submitted_at.isoformat()}


@app.post("/api/client/{token}/contract")
def accept_contract(token: str, payload: ContractAcceptIn, request: Request, db: Session = Depends(get_db)):
    if not payload.agreed:
        raise HTTPException(422, "You must agree before accepting the contract")
    portal = resolve_portal(db, token)
    booking = portal.booking
    if payload.accepted_email.lower() != booking.client.email.lower():
        raise HTTPException(422, "Please use the email address shown on your booking")
    if db.scalar(select(ContractAcceptance).where(ContractAcceptance.booking_id == booking.id)):
        raise HTTPException(409, "This agreement has already been accepted")
    contract = db.scalar(select(ContractTemplate).where(ContractTemplate.brand == booking.brand,
                                                        ContractTemplate.is_active.is_(True)))
    if not contract:
        raise HTTPException(404, "No active agreement is available")
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    row = ContractAcceptance(booking_id=booking.id, contract_title=contract.title,
                             contract_version=contract.version, contract_body=contract.body,
                             accepted_name=payload.accepted_name.strip(),
                             accepted_email=str(payload.accepted_email).lower(),
                             ip_address=forwarded or (request.client.host if request.client else None),
                             user_agent=request.headers.get("user-agent", "")[:500])
    db.add(row)
    for task in db.scalars(select(Task).where(Task.booking_id == booking.id,
                                              Task.title.ilike("%contract%"))).all():
        task.completed = True
    audit(db, "accept_contract", "booking", booking.id,
          {"version": contract.version, "accepted_name": row.accepted_name})
    db.commit()
    return {"ok": True, "accepted_at": row.accepted_at.isoformat()}


def run_due_reminders(db: Session) -> dict:
    today = date.today()
    sent, skipped, failed = 0, 0, 0
    bookings = db.scalars(select(Booking).options(selectinload(Booking.client))
                          .where(Booking.archived_at.is_(None), Booking.status != RecordStatus.CANCELLED)).all()
    for booking in bookings:
        keys: list[str] = []
        if booking.balance_due_date:
            days = (booking.balance_due_date - today).days
            if days == 14:
                keys.append("balance_due_14")
            if days == 7:
                keys.append("balance_due_7")
        if booking.kind == RecordKind.WEDDING and booking.event_date and (booking.event_date - today).days == 30:
            keys.append("final_questionnaire")
        for key in keys:
            if db.scalar(select(ReminderLog).where(ReminderLog.booking_id == booking.id,
                                                   ReminderLog.reminder_key == key,
                                                   ReminderLog.scheduled_for == today)):
                skipped += 1
                continue
            reminder = ReminderLog(booking_id=booking.id, reminder_key=key, scheduled_for=today)
            db.add(reminder)
            template = db.scalar(select(EmailTemplate).where(EmailTemplate.brand == booking.brand,
                                                             EmailTemplate.template_key == key,
                                                             EmailTemplate.is_active.is_(True)))
            profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
            try:
                portal_url = None
                if key == "final_questionnaire":
                    raw, _ = issue_portal_token(db, booking.id, 60)
                    portal_url = f"{settings.app_url.rstrip('/')}/client/{raw}"
                if not template:
                    raise RuntimeError("Reminder template is inactive or missing")
                subject, _ = send_template_email(booking, profile, template, portal_url)
                reminder.status, reminder.sent_at = "sent", datetime.now(timezone.utc)
                db.add(EmailLog(booking_id=booking.id, template_key=key, recipient=booking.client.email,
                                subject=subject, status="sent"))
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

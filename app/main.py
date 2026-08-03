import mimetypes
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .bootstrap import bootstrap
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .migrations import apply_safe_migrations
from .models import (Admin, AuditLog, Booking, BookingNote, Brand, BusinessProfile, Client, Document,
                     Invoice, Payment, RecordKind, Task)
from .pdf import invoice_pdf
from .schemas import (BookingIn, BookingPatch, BusinessPatch, InvoiceIn, LoginIn, NoteIn, PaymentIn,
                      TaskIn, TaskPatch)
from .security import create_token, current_admin, verify_password
from .services import audit, create_default_tasks, dashboard_counts, invoice_status, next_invoice_number

settings = get_settings()
STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_UPLOADS = {"application/pdf", "image/jpeg", "image/png",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    apply_safe_migrations()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        bootstrap(db)
    yield


app = FastAPI(title=settings.app_name, version="2.0.0-phase2a", lifespan=lifespan, docs_url=None, redoc_url=None)


def money(value) -> float:
    return float(value or 0)


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
            "paid": money(item.paid), "balance": money(item.total - item.paid), "status": item.status,
            "client": item.booking.title if item.booking else None,
            "payments": [payment_json(p) for p in sorted(item.payments, key=lambda x: x.paid_date, reverse=True)]}


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
    return {"status": "ok", "phase": "2A"}


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
    audit(db, "update", "booking", item.id, {"fields": list(payload.model_fields_set)})
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
        db.add(Payment(invoice_id=invoice.id, amount=payload.paid,
                       paid_date=booking.deposit_paid_date or payload.issue_date,
                       payment_type="bank_transfer", reference=number, notes="Opening payment"))
    audit(db, "create_invoice", "booking", booking.id, {"number": number})
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
    audit(db, "record_payment", "booking", invoice.booking_id,
          {"invoice": invoice.number, "amount": money(payload.amount)})
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


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")

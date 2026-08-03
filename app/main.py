import mimetypes
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .bootstrap import bootstrap
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .models import Admin, Booking, Brand, BusinessProfile, Client, Document, Invoice, RecordKind, Task
from .schemas import BookingIn, BookingPatch, InvoiceIn, LoginIn, TaskIn, TaskPatch
from .security import create_token, current_admin, verify_password
from .services import audit, create_default_tasks, dashboard_counts, invoice_status, next_invoice_number

settings = get_settings()
STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_UPLOADS = {"application/pdf", "image/jpeg", "image/png", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        bootstrap(db)
    yield


app = FastAPI(title=settings.app_name, version="1.0.0-phase1", lifespan=lifespan, docs_url=None, redoc_url=None)


def money(value) -> float:
    return float(value or 0)


def client_json(client: Client) -> dict:
    return {"id": client.id, "first_name": client.first_name, "last_name": client.last_name, "partner_name": client.partner_name, "company_name": client.company_name, "email": client.email, "phone": client.phone, "address": client.address}


def booking_json(item: Booking, full: bool = False) -> dict:
    data = {"id": item.id, "brand": item.brand.value, "kind": item.kind.value, "status": item.status.value, "title": item.title, "event_date": item.event_date.isoformat() if item.event_date else None, "venue_or_project": item.venue_or_project, "package_name": item.package_name, "quoted_total": money(item.quoted_total), "deposit_amount": money(item.deposit_amount), "deposit_paid_date": item.deposit_paid_date.isoformat() if item.deposit_paid_date else None, "balance_due_date": item.balance_due_date.isoformat() if item.balance_due_date else None, "client": client_json(item.client), "created_at": item.created_at.isoformat()}
    if full:
        data.update({"notes": item.notes, "form_data": item.form_data, "workflow_state": item.workflow_state, "tasks": [{"id": t.id, "title": t.title, "due_at": t.due_at.isoformat() if t.due_at else None, "completed": t.completed, "workflow_key": t.workflow_key} for t in item.tasks], "invoices": [invoice_json(i) for i in item.invoices], "documents": [{"id": d.id, "category": d.category, "original_name": d.original_name, "content_type": d.content_type, "size_bytes": d.size_bytes, "created_at": d.created_at.isoformat()} for d in item.documents]})
    return data


def invoice_json(item: Invoice) -> dict:
    return {"id": item.id, "booking_id": item.booking_id, "brand": item.brand.value, "sequence": item.sequence, "number": item.number, "issue_date": item.issue_date.isoformat(), "supply_date": item.supply_date.isoformat() if item.supply_date else None, "total": money(item.total), "paid": money(item.paid), "balance": money(item.total-item.paid), "status": item.status, "client": item.booking.title if item.booking else None}


@app.get("/api/health")
def health():
    return {"status": "ok", "phase": 1}


@app.post("/api/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    admin = db.scalar(select(Admin).where(Admin.email == payload.email.lower()))
    if not admin or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect")
    response.set_cookie("booking_session", create_token(admin), httponly=True, secure=settings.cookie_secure, samesite="strict", max_age=settings.session_hours*3600, path="/")
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
    return [{"brand": r.brand.value, "display_name": r.display_name, "legal_name": r.legal_name, "invoice_prefix": r.invoice_prefix, "email": r.email} for r in rows]


@app.get("/api/dashboard")
def dashboard(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    counts = dashboard_counts(db)
    upcoming = db.scalars(select(Booking).options(selectinload(Booking.client)).where(Booking.event_date >= date.today()).order_by(Booking.event_date).limit(6)).all()
    tasks = db.scalars(select(Task).options(selectinload(Task.booking)).where(Task.completed.is_(False)).order_by(Task.due_at.asc().nullslast()).limit(8)).all()
    counts.update({"upcoming": [booking_json(x) for x in upcoming], "tasks": [{"id": t.id, "title": t.title, "due_at": t.due_at.isoformat() if t.due_at else None, "booking_title": t.booking.title, "completed": t.completed} for t in tasks]})
    return counts


@app.get("/api/bookings")
def list_bookings(brand: Brand | None = None, kind: RecordKind | None = None, q: str | None = Query(default=None, max_length=100), _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(Booking).options(selectinload(Booking.client)).order_by(Booking.event_date.asc().nullslast(), Booking.created_at.desc())
    if brand:
        stmt = stmt.where(Booking.brand == brand)
    if kind:
        stmt = stmt.where(Booking.kind == kind)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.join(Client).where(or_(Booking.title.ilike(term), Booking.venue_or_project.ilike(term), Client.email.ilike(term), Client.company_name.ilike(term)))
    return [booking_json(x) for x in db.scalars(stmt).unique().all()]


@app.post("/api/bookings", status_code=201)
def create_booking(payload: BookingIn, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    client = Client(**payload.client.model_dump())
    db.add(client)
    db.flush()
    values = payload.model_dump(exclude={"client"})
    booking = Booking(**values, client_id=client.id)
    db.add(booking)
    db.flush()
    create_default_tasks(db, booking.id, booking.kind)
    audit(db, "create", "booking", booking.id, {"title": booking.title, "brand": booking.brand.value})
    db.commit()
    return get_booking(booking.id, _, db)


@app.get("/api/bookings/{booking_id}")
def get_booking(booking_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = db.scalar(select(Booking).options(selectinload(Booking.client), selectinload(Booking.tasks), selectinload(Booking.invoices), selectinload(Booking.documents)).where(Booking.id == booking_id))
    if not item:
        raise HTTPException(404, "Booking not found")
    return booking_json(item, full=True)


@app.patch("/api/bookings/{booking_id}")
def patch_booking(booking_id: str, payload: BookingPatch, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    item = db.get(Booking, booking_id)
    if not item:
        raise HTTPException(404, "Booking not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    audit(db, "update", "booking", item.id, {"fields": list(payload.model_fields_set)})
    db.commit()
    return get_booking(item.id, _, db)


@app.post("/api/bookings/{booking_id}/tasks", status_code=201)
def create_task(booking_id: str, payload: TaskIn, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if not db.get(Booking, booking_id):
        raise HTTPException(404, "Booking not found")
    task = Task(booking_id=booking_id, **payload.model_dump())
    db.add(task); audit(db, "create", "task", task.id); db.commit(); db.refresh(task)
    return {"id": task.id, "title": task.title, "due_at": task.due_at, "completed": task.completed}


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: str, payload: TaskPatch, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    audit(db, "update", "task", task.id); db.commit(); db.refresh(task)
    return {"id": task.id, "title": task.title, "due_at": task.due_at, "completed": task.completed}


@app.get("/api/invoices")
def list_invoices(brand: Brand | None = None, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(Invoice).options(selectinload(Invoice.booking)).order_by(Invoice.sequence.desc())
    if brand:
        stmt = stmt.where(Invoice.brand == brand)
    return [invoice_json(x) for x in db.scalars(stmt).all()]


@app.post("/api/bookings/{booking_id}/invoices", status_code=201)
def create_invoice(booking_id: str, payload: InvoiceIn, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    sequence, number = next_invoice_number(db, booking.brand)
    invoice = Invoice(booking_id=booking.id, brand=booking.brand, sequence=sequence, number=number, status=invoice_status(payload.total, payload.paid), **payload.model_dump())
    db.add(invoice); audit(db, "create", "invoice", invoice.id, {"number": number}); db.commit()
    return invoice_json(invoice)


@app.post("/api/bookings/{booking_id}/documents", status_code=201)
def upload_document(booking_id: str, category: str = Query(pattern="^[a-zA-Z0-9_-]{2,30}$"), file: UploadFile = File(...), _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    if not db.get(Booking, booking_id):
        raise HTTPException(404, "Booking not found")
    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if content_type not in ALLOWED_UPLOADS:
        raise HTTPException(415, "Only PDF, DOCX, JPEG and PNG files are accepted")
    original = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(file.filename or "document").name)[:200]
    suffix = Path(original).suffix.lower()
    storage_name = f"{booking_id}/{category}/{uuid.uuid4().hex}{suffix}"
    target = settings.storage_root / storage_name
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with target.open("wb") as output:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                output.close(); target.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {settings.max_upload_mb}MB limit")
            output.write(chunk)
    document = Document(booking_id=booking_id, category=category, original_name=original, storage_name=storage_name, content_type=content_type, size_bytes=size)
    db.add(document); audit(db, "upload", "document", document.id, {"name": original}); db.commit()
    return {"id": document.id, "category": category, "original_name": original, "size_bytes": size}


@app.get("/api/documents/{document_id}")
def download_document(document_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    path = settings.storage_root / document.storage_name
    if not path.is_file():
        raise HTTPException(404, "Stored file is missing")
    return FileResponse(path, media_type=document.content_type, filename=document.original_name)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


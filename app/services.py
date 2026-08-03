from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuditLog, Booking, Brand, BusinessProfile, Invoice, InvoiceCounter, RecordKind, RecordStatus, Task


def audit(db: Session, action: str, entity_type: str, entity_id: str | None = None, details: dict | None = None) -> None:
    db.add(AuditLog(action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}))


def create_default_tasks(db: Session, booking_id: str, kind: RecordKind) -> None:
    names = ["Send quote", "Receive booking form", "Receive signed contract", "Confirm deposit"]
    if kind == RecordKind.WEDDING:
        names += ["Send final details questionnaire", "Confirm wedding timings", "Prepare gallery delivery"]
    else:
        names += ["Receive website content", "Client review", "Launch website"]
    for position, name in enumerate(names, 1):
        db.add(Task(booking_id=booking_id, title=name, workflow_key=f"step_{position}"))


def next_invoice_number(db: Session, brand: Brand) -> tuple[int, str]:
    settings = get_settings()
    counter = db.execute(select(InvoiceCounter).where(InvoiceCounter.key == "global").with_for_update()).scalar_one_or_none()
    if not counter:
        counter = InvoiceCounter(key="global", value=settings.invoice_start)
        db.add(counter)
        db.flush()
    counter.value += 1
    prefix = db.execute(select(BusinessProfile.invoice_prefix).where(BusinessProfile.brand == brand)).scalar_one()
    return counter.value, f"{prefix}{counter.value:05d}"


def invoice_status(total: Decimal, paid: Decimal) -> str:
    if paid >= total:
        return "paid"
    if paid > 0:
        return "part_paid"
    return "unpaid"


def dashboard_counts(db: Session) -> dict:
    confirmed = db.scalar(select(func.count()).select_from(Booking).where(Booking.status == RecordStatus.CONFIRMED)) or 0
    open_enquiries = db.scalar(select(func.count()).select_from(Booking).where(Booking.status.in_([RecordStatus.ENQUIRY, RecordStatus.QUOTED]))) or 0
    outstanding = db.scalar(select(func.coalesce(func.sum(Invoice.total - Invoice.paid), 0)).where(Invoice.status != "paid")) or 0
    due_tasks = db.scalar(select(func.count()).select_from(Task).where(Task.completed.is_(False))) or 0
    return {"confirmed": confirmed, "open_enquiries": open_enquiries, "outstanding": float(outstanding), "open_tasks": due_tasks, "generated_at": datetime.now(timezone.utc).isoformat()}

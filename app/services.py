from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuditLog, Booking, Brand, BusinessProfile, Invoice, InvoiceCounter, RecordKind, RecordStatus, Task


def audit(db: Session, action: str, entity_type: str, entity_id: str | None = None, details: dict | None = None) -> None:
    db.add(AuditLog(action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}))


def final_details_call_due(event_date: date | None) -> datetime | None:
    if not event_date:
        return None
    return datetime.combine(event_date - timedelta(days=30), time(hour=10), tzinfo=timezone.utc)


def create_default_tasks(db: Session, booking_id: str, kind: RecordKind,
                         event_date: date | None = None) -> None:
    if kind == RecordKind.WEDDING:
        # Payment reminders and the two pre-wedding check-ins are automatic.
        # Keep only the three things Mark may genuinely need to chase by hand.
        tasks = [
            ("Send package quote", "wbm_quote", None),
            ("Booking form completed", "wbm_booking_form", None),
            ("Wedding contract signed", "wbm_contract", None),
            ("Finalise wedding details by phone", "wbm_final_details_call",
             final_details_call_due(event_date)),
        ]
    else:
        names = ["Send quote", "Receive booking form", "Receive signed contract", "Confirm deposit",
                 "Receive website content", "Client review", "Launch website"]
        tasks = [(name, f"digital_step_{position}", None) for position, name in enumerate(names, 1)]
    for name, workflow_key, due_at in tasks:
        db.add(Task(booking_id=booking_id, title=name, workflow_key=workflow_key, due_at=due_at))


def sync_final_details_call_task(db: Session, booking: Booking) -> Task | None:
    """Keep the private phone-call reminder aligned with the wedding date."""
    if booking.kind != RecordKind.WEDDING:
        return None
    task = db.scalar(select(Task).where(
        Task.booking_id == booking.id,
        Task.workflow_key == "wbm_final_details_call",
    ).limit(1))
    if not task:
        task = Task(booking_id=booking.id, title="Finalise wedding details by phone",
                    workflow_key="wbm_final_details_call")
        db.add(task)
    task.title = "Finalise wedding details by phone"
    task.due_at = final_details_call_due(booking.event_date)
    return task


def visible_task_condition():
    """Hide only old generated Studio Ninja tasks; retain any manual task Mark adds."""
    return or_(
        Booking.legacy_source.is_(None),
        Booking.legacy_source != "studio_ninja",
        Task.workflow_key.is_(None),
        ~Task.workflow_key.like("step_%"),
    )


def next_invoice_number(db: Session, brand: Brand) -> tuple[int, str]:
    settings = get_settings()
    counter_key = f"brand:{brand.value}"
    counter = db.execute(
        select(InvoiceCounter).where(InvoiceCounter.key == counter_key).with_for_update()
    ).scalar_one_or_none()
    if not counter:
        highest_existing = db.scalar(
            select(func.max(Invoice.sequence)).where(Invoice.brand == brand)
        ) or settings.invoice_start
        counter = InvoiceCounter(
            key=counter_key,
            value=max(settings.invoice_start, int(highest_existing)),
        )
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
    confirmed = db.scalar(select(func.count()).select_from(Booking).where(Booking.archived_at.is_(None), Booking.status == RecordStatus.CONFIRMED)) or 0
    open_enquiries = db.scalar(select(func.count()).select_from(Booking).where(Booking.archived_at.is_(None), Booking.status.in_([RecordStatus.ENQUIRY, RecordStatus.QUOTED]))) or 0
    outstanding = db.scalar(select(func.coalesce(func.sum(Invoice.total - Invoice.paid), 0))
                            .where(~Invoice.status.in_(["paid", "void"]))) or 0
    due_tasks = db.scalar(select(func.count()).select_from(Task).join(Booking).where(
        Booking.archived_at.is_(None), Booking.status != RecordStatus.CANCELLED,
        Task.completed.is_(False), visible_task_condition())) or 0
    return {"confirmed": confirmed, "open_enquiries": open_enquiries, "outstanding": float(outstanding), "open_tasks": due_tasks, "generated_at": datetime.now(timezone.utc).isoformat()}

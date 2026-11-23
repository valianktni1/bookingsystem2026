"""Ivory-only recurring invoices. Generation never sends mail or records payment."""
from __future__ import annotations

import asyncio
import calendar
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .business_time import business_today
from .database import Base, SessionLocal, get_db
from .models import Admin, Booking, Brand, Invoice, RecordKind, RecordStatus, uid
from .security import current_admin
from .services import audit, next_invoice_number

LABELS = {1: "Monthly", 3: "Quarterly", 6: "Six-monthly", 12: "Annually"}
INVOICE_LEAD = timedelta(days=7)
logger = logging.getLogger(__name__)


class RecurringTerms(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interval_months: Literal[1, 3, 6, 12]
    start_date: date
    due_days: int = Field(default=0, ge=0, le=90)
    cycle_total: Decimal | None = Field(default=None, gt=0, le=999999, decimal_places=2)
    issue_first_on_acceptance: bool = False
    issue_seven_days_early: bool = False


class RecurringPlan(Base):
    __tablename__ = "ivory_recurring_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_offer_id: Mapped[str] = mapped_column(ForeignKey("ivory_offers.id", ondelete="CASCADE"), unique=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    interval_months: Mapped[int]
    start_date: Mapped[date] = mapped_column(Date)
    due_days: Mapped[int] = mapped_column(default=0)
    cycle_total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    details: Mapped[dict] = mapped_column(JSON)
    next_cycle: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class RecurringCycle(Base):
    __tablename__ = "ivory_recurring_cycles"
    __table_args__ = (UniqueConstraint("plan_id", "cycle_index", name="uq_ivory_recurring_period"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("ivory_recurring_plans.id", ondelete="CASCADE"), index=True)
    cycle_index: Mapped[int]
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, unique=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)


def cycle_start(anchor: date, interval: int, index: int) -> date:
    """Calculate from the original anchor, preserving Jan 31 / leap-year intent."""
    month = anchor.year * 12 + anchor.month - 1 + interval * index
    year, month = divmod(month, 12)
    month += 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def billing_summary(details: dict) -> dict | None:
    billing = details.get("billing")
    if not billing:
        return None
    rate = sum((Decimal(str(x["amount"])) for x in details["lines"] if x["selected"] and x["kind"] == "monthly"), Decimal("0"))
    total = Decimal(str(billing["cycle_total"])) if billing.get("cycle_total") is not None else rate * billing["interval_months"]
    return {**billing, "label": LABELS[billing["interval_months"]], "cycle_total": str(total.quantize(Decimal("0.01")))}


def billing_text(details: dict) -> str:
    billing = billing_summary(details)
    if not billing:
        return ""
    start = date.fromisoformat(str(billing["start_date"]))
    timing = f"The standard payment allowance is {billing['due_days']} day(s) after issue. "
    if billing.get("issue_seven_days_early"):
        timing = ("Invoices are prepared seven days before each service period starts. "
                  f"Payment is due {billing['due_days']} day(s) after the service period starts. ")
    first_invoice = ""
    if billing.get("issue_first_on_acceptance"):
        first_invoice = "The first invoice is issued on acceptance. "
        if not billing.get("issue_seven_days_early"):
            first_invoice += ("Its payment allowance runs from the service start date "
                              "or invoice issue date, whichever is later. ")
    return (f"Recurring services: £{Decimal(billing['cycle_total']):,.2f} every {billing['interval_months']} month(s), "
            f"starting {start:%d %B %Y}. Each invoice covers {billing['interval_months']} month(s). "
            f"{timing}{first_invoice}This is separate from any one-off work. "
            "Payments are recorded only when received; no automatic card or bank collection is made.")


def plan_for_offer(db, offer_id):
    return db.scalar(select(RecurringPlan).where(RecurringPlan.source_offer_id == offer_id))


def issue_seven_days_early(plan):
    return bool((plan.details.get("billing") or {}).get("issue_seven_days_early"))


def public_plan(plan):
    start = cycle_start(plan.start_date, plan.interval_months, plan.next_cycle)
    early = issue_seven_days_early(plan)
    return {"id": plan.id, "status": plan.status, "interval_months": plan.interval_months,
            "cycle_total": float(plan.cycle_total), "start_date": plan.start_date.isoformat(),
            "next_billing_date": start.isoformat(), "issue_seven_days_early": early,
            "next_invoice_date": (start - INVOICE_LEAD if early else start).isoformat(),
            "next_due_date": (start + timedelta(days=plan.due_days)).isoformat() if early else None}


def _booking(db, booking_id):
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if (not booking or booking.brand != Brand.IVORY or booking.kind != RecordKind.DIGITAL
            or booking.legacy_source or booking.archived_at or booking.status == RecordStatus.CANCELLED):
        raise HTTPException(409, "Recurring billing requires an active native Ivory Digital project.")
    return booking


def cycle_document(plan, index):
    start = cycle_start(plan.start_date, plan.interval_months, index)
    end = cycle_start(plan.start_date, plan.interval_months, index + 1) - timedelta(days=1)
    period = f"Service period: {start:%d %B %Y} to {end:%d %B %Y}"
    services = "\n\n".join(x["name"] + ("\n" + x["description"] if x["description"] else "")
                             for x in plan.details["lines"] if x["selected"] and x["kind"] == "monthly")
    line = {"type": "service", "name": plan.title, "description": period + "\n\n" + services,
            "kind": "one_off", "quantity": 1, "unit_price": float(plan.cycle_total), "total": float(plan.cycle_total)}
    return start, end, period, line


def generate_cycle(db, plan, *, today=None, allow_missed=False, issue_on_acceptance=False):
    """Caller holds a plan row lock; period uniqueness protects retries as well."""
    today = today or business_today()
    if plan.status != "active":
        return None
    start, end, period, line = cycle_document(plan, plan.next_cycle)
    early = issue_seven_days_early(plan)
    issue_from = start - INVOICE_LEAD if early else start
    if issue_from > today and not (issue_on_acceptance and plan.next_cycle == 0):
        return None
    if end < today and not allow_missed:
        plan.last_error = "A whole billing period was missed. Review it and create the next invoice manually."
        return None
    booking = _booking(db, plan.booking_id)
    previous = db.scalar(select(RecurringCycle).where(RecurringCycle.plan_id == plan.id,
                                                    RecurringCycle.cycle_index == plan.next_cycle))
    if previous:
        plan.next_cycle += 1
        return None
    from .ivory_quotes import profile_for
    profile = profile_for(db)
    bank = dict(profile.bank_details or {})
    if not (bank.get("account_number") and bank.get("sort_code")):
        raise HTTPException(422, "Save Ivory Digital bank details before creating a recurring invoice.")
    seq, number = next_invoice_number(db, Brand.IVORY)
    due_from = start if early else max(today, start)
    invoice = Invoice(booking_id=booking.id, brand=Brand.IVORY, sequence=seq, number=number,
                      issue_date=today, supply_date=start, due_date=due_from + timedelta(days=plan.due_days),
                      description=plan.title, notes=plan.details["terms"] + "\n\n" + period,
                      total=plan.cycle_total, paid=Decimal("0"), status="unpaid", line_items=[line])
    db.add(invoice)
    db.flush()
    # Freeze recipient, service scope and bank details with every issued invoice.
    workflow = dict(booking.workflow_state or {})
    workflow["invoice_bank_details"] = {**workflow.get("invoice_bank_details", {}), invoice.id: bank}
    workflow["ivory_invoice_metadata"] = {**workflow.get("ivory_invoice_metadata", {}), invoice.id: {
        "customer": plan.details["customer"], "email": plan.details["email"], "address": plan.details["address"],
        "intro": period, "terms": invoice.notes, "monthly": "0", "recurring_plan_id": plan.id}}
    booking.workflow_state = workflow
    db.add(RecurringCycle(plan_id=plan.id, cycle_index=plan.next_cycle, invoice_id=invoice.id,
                          period_start=start, period_end=end))
    audit(db, "ivory_recurring_invoice_created", "booking", booking.id,
          {"plan_id": plan.id, "invoice": number, "period_start": start.isoformat(), "period_end": end.isoformat()})
    plan.next_cycle += 1
    plan.last_error = None
    db.flush()
    return invoice


def start_plan(db, offer):
    """Acceptance starts a schedule once; drafts/shares/previews do not."""
    if not offer.contents.get("billing"):
        return None, None
    plan = plan_for_offer(db, offer.id)
    if plan:
        return plan, None
    _booking(db, offer.booking_id)
    billing = billing_summary(offer.contents)
    plan = RecurringPlan(source_offer_id=offer.id, booking_id=offer.booking_id, title=offer.contents["title"],
                         interval_months=billing["interval_months"], start_date=date.fromisoformat(billing["start_date"]),
                         due_days=billing["due_days"], cycle_total=Decimal(billing["cycle_total"]),
                         details=offer.contents, next_cycle=0, status="active")
    db.add(plan)
    db.flush()
    audit(db, "ivory_recurring_started", "booking", plan.booking_id, {"plan_id": plan.id, "billing": billing})
    return plan, generate_cycle(db, plan, issue_on_acceptance=billing.get("issue_first_on_acceptance", False))


def run_due_cycles(*, today=None, sessions=SessionLocal):
    """Each plan has its own transaction; one invalid project cannot block others."""
    today = today or business_today()
    with sessions() as db:
        ids = list(db.scalars(select(RecurringPlan.id).where(RecurringPlan.status == "active")))
    count = 0
    for plan_id in ids:
        with sessions() as db:
            try:
                plan = db.scalar(select(RecurringPlan).where(RecurringPlan.id == plan_id).with_for_update())
                created = bool(plan and generate_cycle(db, plan, today=today))
                db.commit()
                if created:
                    count += 1
            except IntegrityError:
                db.rollback()  # Another worker already issued this exact period.
            except Exception as exc:
                db.rollback()
                logger.warning("Recurring invoice generation requires review for plan %s", plan_id)
                plan = db.get(RecurringPlan, plan_id)
                if plan:
                    plan.last_error = (str(exc.detail) if isinstance(exc, HTTPException) else "Invoice generation failed; review the schedule before retrying.")[:500]
                    db.commit()
    return count


async def recurring_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(run_due_cycles)
        except Exception:
            logger.exception("Recurring invoice scan failed; it will retry next minute")


class PlanAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "cancel", "generate"]
    expected_cycle: int = Field(ge=0)


class PlanEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    cycle_total: Decimal = Field(gt=0, le=999999, decimal_places=2)
    terms: str = Field(max_length=4000)
    description: str = Field(min_length=1, max_length=4000)
    issue_seven_days_early: bool | None = None
    expected_cycle: int = Field(ge=0)
    confirmed: Literal[True]


def recurring_description(plan):
    return "\n\n".join(x["name"] + "\n" + x["description"]
                       for x in plan.details["lines"] if x["selected"] and x["kind"] == "monthly")


def register_routes(app):
    def get(db, plan_id):
        plan = db.scalar(select(RecurringPlan).where(RecurringPlan.id == plan_id).with_for_update())
        if not plan:
            raise HTTPException(404, "Recurring schedule not found")
        return plan

    @app.get("/api/ivory-recurring")
    def plans(_: Admin = Depends(current_admin), db=Depends(get_db)):
        result = []
        for plan in db.scalars(select(RecurringPlan).order_by(RecurringPlan.start_date.desc())):
            cycles = list(db.scalars(select(RecurringCycle).where(RecurringCycle.plan_id == plan.id).order_by(RecurringCycle.cycle_index.desc())))
            invoices = []
            for cycle in cycles:
                invoice = db.get(Invoice, cycle.invoice_id) if cycle.invoice_id else None
                invoices.append({"id": cycle.invoice_id, "number": invoice.number if invoice else "Retained period",
                                 "status": invoice.status if invoice else "removed", "balance": float(invoice.total - invoice.paid) if invoice else 0,
                                 "period_start": cycle.period_start.isoformat(), "period_end": cycle.period_end.isoformat()})
            result.append({**public_plan(plan), "booking_id": plan.booking_id, "title": plan.title,
                           "customer": plan.details["customer"], "email": plan.details["email"],
                           "next_cycle": plan.next_cycle, "due_days": plan.due_days, "terms": plan.details["terms"],
                           "description": recurring_description(plan),
                           "last_error": plan.last_error, "invoices": invoices})
        return result

    @app.post("/api/ivory-recurring/{plan_id}/action")
    def action(plan_id: str, payload: PlanAction, _: Admin = Depends(current_admin), db=Depends(get_db)):
        plan = get(db, plan_id)
        if plan.next_cycle != payload.expected_cycle:
            raise HTTPException(409, "This schedule changed. Refresh and review it before trying again.")
        if plan.status == "cancelled":
            raise HTTPException(409, "This schedule is cancelled. Create a new quote to restart billing.")
        invoice = None
        if payload.action == "pause":
            plan.status = "paused"
        elif payload.action == "cancel":
            plan.status = "cancelled"
        elif payload.action == "resume":
            _booking(db, plan.booking_id)
            if plan.status != "paused":
                raise HTTPException(409, "Only a paused schedule can be resumed.")
            # Paused periods stay unbilled. Resume at the next anchor date.
            while cycle_start(plan.start_date, plan.interval_months, plan.next_cycle) < business_today():
                plan.next_cycle += 1
            plan.status = "active"
            plan.last_error = None
        elif payload.action == "generate":
            if plan.status != "active":
                raise HTTPException(409, "Resume the schedule before generating an invoice.")
            invoice = generate_cycle(db, plan, allow_missed=True)
            if not invoice:
                raise HTTPException(409, "The next invoice is not due yet, or this period is already recorded.")
        audit(db, "ivory_recurring_" + payload.action, "booking", plan.booking_id,
              {"plan_id": plan.id, "previous_cycle": payload.expected_cycle, "next_cycle": plan.next_cycle})
        db.commit()
        return {**public_plan(plan), "invoice_number": invoice.number if invoice else None}

    @app.put("/api/ivory-recurring/{plan_id}")
    def edit(plan_id: str, payload: PlanEdit, _: Admin = Depends(current_admin), db=Depends(get_db)):
        plan = get(db, plan_id)
        if plan.status == "cancelled" or plan.next_cycle != payload.expected_cycle:
            raise HTTPException(409, "Refresh and review this schedule before editing it.")
        old_total = str(plan.cycle_total)
        service_changed = (payload.title.strip() != plan.title or payload.cycle_total != plan.cycle_total
                           or payload.description.strip() != recurring_description(plan).strip())
        plan.title = payload.title.strip()
        plan.cycle_total = payload.cycle_total
        details = {**plan.details, "terms": payload.terms}
        if service_changed:
            details["lines"] = [{"name": plan.title, "description": payload.description,
                                 "amount": str(payload.cycle_total / plan.interval_months),
                                 "selected": True, "kind": "monthly"}]
        if payload.issue_seven_days_early is not None:
            details["billing"] = {**(details.get("billing") or {}),
                                  "issue_seven_days_early": payload.issue_seven_days_early}
        plan.details = details
        audit(db, "ivory_recurring_edited", "booking", plan.booking_id,
              {"plan_id": plan.id, "previous_total": old_total, "new_total": str(plan.cycle_total),
               "from_cycle": plan.next_cycle, "issue_seven_days_early": issue_seven_days_early(plan)})
        db.commit()
        return public_plan(plan)

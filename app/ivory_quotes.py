"""Versioned Ivory offers. Invoice and payment writes happen only on acceptance."""
import hashlib
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .business_time import business_today
from .config import get_settings
from .database import Base, get_db
from .models import Admin, Booking, Brand, BusinessProfile, Client, Invoice, Payment, RecordKind, RecordStatus, SystemSetting, now, uid
from .quote_templates import capture_invoice_bank
from .security import current_admin
from .services import audit, invoice_status, next_invoice_number
from .ivory_recurring import RecurringCycle, RecurringTerms, billing_summary, plan_for_offer, public_plan, start_plan

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Money = Annotated[Decimal, Field(ge=0, le=999999, decimal_places=2)]
KEY = "ivory_service_templates"


class IvoryOffer(Base):
    __tablename__ = "ivory_offers"
    __table_args__ = (UniqueConstraint("group_id", "revision", name="uq_ivory_offer_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    group_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    contents: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acceptance: Mapped[dict] = mapped_column(JSON, default=dict)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceLine(Strict):
    name: Text
    description: str = Field(default="", max_length=4000)
    amount: Money
    kind: Literal["one_off", "included", "monthly"] = "one_off"
    selected: bool = True


class Template(Strict):
    name: Text
    intro: str = Field(default="", max_length=2000)
    terms: str = Field(default="Balance due before launch. No VAT charged.", max_length=4000)
    lines: list[ServiceLine] = Field(min_length=1, max_length=40)


class TemplateList(Strict):
    items: list[Template] = Field(max_length=50)


class OfferDetails(Strict):
    title: Text
    customer: Text
    email: EmailStr
    address: str = Field(default="", max_length=1000)
    intro: str = Field(default="", max_length=2000)
    terms: str = Field(default="Balance due before launch. No VAT charged.", max_length=4000)
    lines: list[ServiceLine] = Field(min_length=1, max_length=40)
    due_date: date | None = None
    opening_paid: Money = Decimal("0")
    opening_paid_date: date | None = None
    change_reason: str = Field(default="", max_length=1000)
    billing: RecurringTerms | None = None

    @model_validator(mode="after")
    def check_amounts(self):
        total = sum(line.amount for line in self.lines if line.selected and line.kind == "one_off")
        monthly = sum(line.amount for line in self.lines if line.selected and line.kind == "monthly")
        if self.billing and monthly <= 0:
            raise ValueError("Select at least one monthly service with a monthly rate for recurring billing.")
        if self.billing and self.billing.start_date.year > 2090:
            raise ValueError("Choose a recurring start date before 2091.")
        if self.billing and not self.billing.cycle_total and monthly * self.billing.interval_months > 999999:
            raise ValueError("The recurring period total must be no more than £999,999.")
        if total <= 0 and not self.billing:
            raise ValueError("Add at least one selected one-off service with a price.")
        if self.opening_paid > total:
            raise ValueError("The payment cannot be more than the one-off total.")
        if self.opening_paid and (not self.opening_paid_date or self.opening_paid_date > business_today()):
            raise ValueError("Enter the date the opening payment was received, on or before today.")
        if not self.opening_paid:
            self.opening_paid_date = None
        return self


class NewOffer(Strict):
    request_id: UUID
    booking_id: str | None = Field(default=None, max_length=36)
    details: OfferDetails


class Agreement(Strict):
    name: Text
    confirmed: Literal[True]
    note: str = Field(default="", max_length=1000)


STARTER = {
    "title": "Website design and agreed additions", "customer": "The Kitchen Factory Liverpool", "email": "", "address": "",
    "intro": "Website design and build for your Liverpool showroom, with the additional supplier range and approved trade accounts agreed separately.",
    "terms": "Balance due before launch. No VAT charged. Additional website pages already created are included at no extra charge. Optional hosting and SEO are separate monthly services and are not included in this invoice.",
    "opening_paid": "599.50", "opening_paid_date": "2026-10-19",
    "lines": [
        {"name": "Original website design and build", "description": "WordPress / Elementor website with unlimited pages, mobile layout, copy based on supplied information, quote form, up to four project galleries, domain connection, basic SEO and two revision rounds. Product showcase with up to 12 launch listings and a handover included. Additional pages already created at no extra charge.", "amount": "1199.00", "kind": "one_off", "selected": True},
        {"name": "Additional supplier collection content", "description": "Additional supplier range: organise supplied images, collection details and specifications. Remaining content awaits supplier information; final range count to be agreed.", "amount": "150.00", "kind": "one_off", "selected": True},
        {"name": "Approved trade accounts and pricing", "description": "Trade application, approval after vetting, account invitation and login access to trade prices. One trade pricing level. Online ordering and paid licences quoted separately.", "amount": "300.00", "kind": "one_off", "selected": True},
    ],
}
DEFAULTS = [Template(name="Website design", intro="Your new website, built around your business.", lines=[
    ServiceLine(name="Website design and build", description="Describe the agreed pages, content and handover.", amount=1199),
    ServiceLine(name="Managed hosting and care", description="Separate monthly service, starting at launch if selected.", amount=35, kind="monthly", selected=False),
    ServiceLine(name="Local SEO", description="Separate monthly service, starting at launch if selected.", amount=60, kind="monthly", selected=False),
])]


def totals(details):
    lines = details["lines"]
    return (sum((Decimal(str(x["amount"])) for x in lines if x["selected"] and x["kind"] == "one_off"), Decimal("0")),
            sum((Decimal(str(x["amount"])) for x in lines if x["selected"] and x["kind"] == "monthly"), Decimal("0")))


def profile_for(db):
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == Brand.IVORY))
    if not profile:
        raise HTTPException(422, "Complete your Ivory Digital business settings first.")
    return profile


def invoice_for(db, row):
    if row.invoice_id:
        return db.get(Invoice, row.invoice_id)
    d = row.contents
    booking = db.scalar(select(Booking).where(Booking.id == row.booking_id).with_for_update())
    if not booking or booking.archived_at or booking.legacy_source:
        raise HTTPException(409, "This project is no longer available for invoicing.")
    if Decimal(d["opening_paid"]) and db.scalar(select(Invoice.id).where(Invoice.booking_id == booking.id, Invoice.paid > 0)):
        raise HTTPException(409, "An invoice on this project already has a payment. Review it before recording this opening payment again.")
    profile = profile_for(db)
    bank = profile.bank_details or {}
    if not (bank.get("account_number") and bank.get("sort_code")):
        raise HTTPException(422, "Save Ivory Digital bank details in Business settings before creating this invoice.")
    total, monthly = totals(d)
    seq, number = next_invoice_number(db, Brand.IVORY)
    paid = Decimal(d["opening_paid"])
    invoice = Invoice(booking_id=booking.id, brand=Brand.IVORY, sequence=seq, number=number,
                      issue_date=business_today(), due_date=date.fromisoformat(d["due_date"]) if d.get("due_date") else None,
                      description=d["title"], notes=d["terms"], total=total, paid=paid, status=invoice_status(total, paid),
                      line_items=[{"type":"service", "name":x["name"], "description":x["description"],
                                   "kind":x["kind"], "quantity":1, "unit_price":float(Decimal(x["amount"])) if x["kind"] == "one_off" else 0,
                                   "total":float(Decimal(x["amount"])) if x["kind"] == "one_off" else 0}
                                  for x in d["lines"] if x["selected"] and x["kind"] in ("one_off", "included")])
    db.add(invoice); db.flush()
    capture_invoice_bank(booking, invoice)
    bank_workflow = dict(booking.workflow_state or {})
    bank_workflow["invoice_bank_details"] = {**bank_workflow.get("invoice_bank_details", {}), invoice.id: dict(bank)}
    booking.workflow_state = bank_workflow
    snapshot = {"customer": d["customer"], "email": d["email"], "address": d["address"], "intro": d["intro"], "terms": d["terms"],
                "quote_reference": f"IDQ-{row.group_id[:8].upper()}-R{row.revision}", "monthly": str(monthly)}
    wf = dict(booking.workflow_state or {})
    wf["ivory_invoice_metadata"] = {**wf.get("ivory_invoice_metadata", {}), invoice.id: snapshot}
    booking.workflow_state = wf
    if paid:
        db.add(Payment(invoice_id=invoice.id, amount=paid, paid_date=date.fromisoformat(d["opening_paid_date"]),
                       payment_type="bank_transfer", reference=number, notes="Opening payment already received before this invoice was issued."))
    row.invoice_id = invoice.id
    audit(db, "ivory_invoice_created", "booking", booking.id, {"invoice_id": invoice.id, "number": number})
    return invoice


def offer_json(db, row):
    total, monthly = totals(row.contents)
    inv = db.get(Invoice, row.invoice_id) if row.invoice_id else None
    plan = plan_for_offer(db, row.id)
    if inv is None and total == 0 and plan:
        cycle = db.scalar(select(RecurringCycle).where(RecurringCycle.plan_id == plan.id,
                                                      RecurringCycle.invoice_id.is_not(None)).order_by(RecurringCycle.cycle_index).limit(1))
        if cycle:
            inv = db.get(Invoice, cycle.invoice_id)
    return {"id":row.id, "booking_id":row.booking_id, "revision":row.revision, "reference":f"IDQ-{row.group_id[:8].upper()}-R{row.revision}",
            "status":row.status, "details":row.contents, "total":float(total), "monthly":float(monthly),
            "billing":billing_summary(row.contents), "recurring":public_plan(plan) if plan else None,
            "acceptance":row.acceptance, "invoice":({"id":inv.id, "number":inv.number,"total":float(inv.total),"paid":float(inv.paid),
            "balance":float(inv.total-inv.paid)} if inv else None)}


def accept_services(db, row):
    total, _ = totals(row.contents)
    invoice = invoice_for(db, row) if total > 0 else None
    _, recurring_invoice = start_plan(db, row)
    if invoice is None and recurring_invoice is not None:
        row.invoice_id = recurring_invoice.id
        invoice = recurring_invoice
    return invoice


def register_routes(app):
    from pathlib import Path
    from .ivory_pdf import offer_pdf

    def get(db, offer_id, lock=False):
        query = select(IvoryOffer).where(IvoryOffer.id == offer_id)
        row = db.scalar(query.with_for_update() if lock else query)
        if not row:
            raise HTTPException(404, "Quote not found")
        return row

    def public(db, token, lock=False):
        digest = hashlib.sha256(token.encode()).hexdigest()
        query = select(IvoryOffer).where(IvoryOffer.token_hash == digest)
        row = db.scalar(query.with_for_update() if lock else query)
        if not row or row.status not in ("shared", "accepted"):
            raise HTTPException(404, "This quote is no longer available. Ask Mark for the latest version.")
        return row

    @app.get("/api/ivory-quotes/templates")
    def templates(_: Admin = Depends(current_admin), db=Depends(get_db)):
        row = db.get(SystemSetting, KEY)
        return row.value if row else {"items":[x.model_dump(mode="json") for x in DEFAULTS]}

    @app.put("/api/ivory-quotes/templates")
    def save_templates(payload: TemplateList, _: Admin = Depends(current_admin), db=Depends(get_db)):
        row = db.get(SystemSetting, KEY)
        if row is None:
            row = SystemSetting(key=KEY); db.add(row)
        row.value = payload.model_dump(mode="json"); db.commit()
        return row.value

    @app.get("/api/ivory-quotes/projects")
    def projects(_: Admin = Depends(current_admin), db=Depends(get_db)):
        rows = db.scalars(select(Booking).where(Booking.brand == Brand.IVORY, Booking.kind == RecordKind.DIGITAL,
                         Booking.legacy_source.is_(None), Booking.archived_at.is_(None)).order_by(Booking.title).limit(500))
        return [{"id":row.id,"title":row.title,"email":row.client.email,"customer":row.client.company_name or row.title,
                 "address":row.client.address or ""} for row in rows]

    @app.get("/api/ivory-quotes/starter")
    def starter(_: Admin = Depends(current_admin)):
        return STARTER

    @app.get("/api/ivory-quotes")
    def offers(_: Admin = Depends(current_admin), db=Depends(get_db)):
        return [offer_json(db, row) for row in db.scalars(select(IvoryOffer).order_by(IvoryOffer.created_at.desc()).limit(200))]

    @app.post("/api/ivory-quotes", status_code=201)
    def create(payload: NewOffer, _: Admin = Depends(current_admin), db=Depends(get_db)):
        prior = db.scalar(select(IvoryOffer).where(IvoryOffer.request_key == str(payload.request_id)))
        if prior:
            return offer_json(db, prior)
        profile_for(db)
        d = payload.details
        if d.billing and d.billing.start_date < business_today():
            raise HTTPException(422, "Choose today or a future date to start recurring billing.")
        if payload.booking_id:
            booking = db.scalar(select(Booking).where(Booking.id == payload.booking_id).with_for_update())
            if not booking or booking.brand != Brand.IVORY or booking.legacy_source or booking.archived_at:
                raise HTTPException(422, "Choose an active native Ivory Digital project.")
            if str(d.email).lower() != booking.client.email.lower():
                raise HTTPException(422, "Use this project’s saved email address, or update the project contact first.")
            if d.opening_paid and db.scalar(select(Invoice.id).where(Invoice.booking_id == booking.id, Invoice.paid > 0)):
                raise HTTPException(409, "This project already has a paid invoice. Add services with no opening payment, or review its invoices first.")
        else:
            client = Client(first_name=d.customer[:100], last_name="", company_name=d.customer, email=str(d.email), address=d.address or None)
            db.add(client); db.flush()
            booking = Booking(brand=Brand.IVORY, kind=RecordKind.DIGITAL, status=RecordStatus.QUOTED,
                              title=d.customer, client_id=client.id, automation_suppressed=False, workflow_state={"source":"ivory_quote"})
            db.add(booking); db.flush()
        row = IvoryOffer(group_id=uid(), request_key=str(payload.request_id), booking_id=booking.id, contents=d.model_dump(mode="json"))
        db.add(row); db.flush()
        audit(db, "ivory_quote_created", "booking", booking.id, {"offer_id":row.id})
        db.commit()
        return offer_json(db, row)

    @app.post("/api/ivory-quotes/{offer_id}/revise", status_code=201)
    def revise(offer_id: str, payload: NewOffer, _: Admin = Depends(current_admin), db=Depends(get_db)):
        old = get(db, offer_id, True)
        prior = db.scalar(select(IvoryOffer).where(IvoryOffer.request_key == str(payload.request_id)))
        if prior:
            return offer_json(db, prior)
        if old.status == "accepted" or old.invoice_id:
            raise HTTPException(409, "This quote is invoiced. Create an additional-services quote to keep its invoice and payments intact.")
        if old.status == "superseded":
            raise HTTPException(409, "Open the latest revision before editing.")
        if not payload.details.change_reason.strip():
            raise HTTPException(422, "Enter a short reason for the revision.")
        if payload.details.billing and payload.details.billing.start_date < business_today():
            raise HTTPException(422, "Choose today or a future date to start recurring billing.")
        booking = db.get(Booking, old.booking_id)
        if str(payload.details.email).lower() != booking.client.email.lower():
            raise HTTPException(422, "Update the project contact before changing the quote recipient.")
        old.status = "superseded"; old.token_hash = None
        row = IvoryOffer(group_id=old.group_id, revision=old.revision+1, request_key=str(payload.request_id),
                         booking_id=old.booking_id, contents=payload.details.model_dump(mode="json"))
        db.add(row); db.flush(); db.commit()
        return offer_json(db, row)

    @app.post("/api/ivory-quotes/{offer_id}/share")
    def share(offer_id: str, _: Admin = Depends(current_admin), db=Depends(get_db)):
        row = get(db, offer_id, True)
        if row.status not in ("draft", "shared"):
            raise HTTPException(409, "Only the current unaccepted quote can be shared.")
        token = secrets.token_urlsafe(32)
        row.token_hash = hashlib.sha256(token.encode()).hexdigest(); row.status = "shared"; db.commit()
        return {"url":f"{get_settings().app_url.rstrip('/')}/ivory-quote/{token}"}

    @app.post("/api/ivory-quotes/{offer_id}/accept")
    def manual_accept(offer_id: str, payload: Agreement, admin: Admin = Depends(current_admin), db=Depends(get_db)):
        row = get(db, offer_id, True)
        if row.status == "accepted":
            return offer_json(db, row)
        if row.status not in ("draft", "shared"):
            raise HTTPException(409, "Open the latest quote before recording agreement.")
        if not payload.note.strip():
            raise HTTPException(422, "Record what was agreed and when.")
        accept_services(db, row)
        row.status = "accepted"; row.accepted_at = now()
        row.acceptance = {"method":"recorded_by_admin", "name":payload.name, "note":payload.note, "recorded_by":admin.email}
        db.commit()
        return offer_json(db, row)

    @app.get("/api/ivory-quotes/{offer_id}/invoice-preview.pdf")
    def preview_invoice(offer_id: str, _: Admin = Depends(current_admin), db=Depends(get_db)):
        from types import SimpleNamespace
        from .ivory_pdf import document
        row = get(db, offer_id)
        d = row.contents
        profile = profile_for(db)
        payments = ([SimpleNamespace(paid_date=date.fromisoformat(d["opening_paid_date"]), amount=Decimal(d["opening_paid"]))]
                    if Decimal(d["opening_paid"]) else [])
        if totals(d)[0] == 0 and d.get("billing"):
            from .ivory_recurring import RecurringPlan, cycle_document
            billing = billing_summary(d)
            plan = RecurringPlan(title=d["title"], interval_months=billing["interval_months"],
                                 start_date=date.fromisoformat(billing["start_date"]), cycle_total=Decimal(billing["cycle_total"]), details=d)
            start, _, period, line = cycle_document(plan, 0)
            today = business_today()
            due = (max(today, start) + timedelta(days=billing["due_days"])
                   if billing.get("issue_first_on_acceptance") else None)
            content = document(profile, title="INVOICE PREVIEW", reference="WBM number assigned on creation",
                               customer=d["customer"], email=d["email"], address=d["address"], intro=period,
                               lines=[{**line, "amount":line["total"]}], terms=d["terms"], issued=today, due=due,
                               invoice=True, bank=profile.bank_details)
            return Response(content, media_type="application/pdf", headers={"Cache-Control":"no-store"})
        content = document(profile, title="INVOICE PREVIEW", reference="WBM number assigned on creation", customer=d["customer"],
                           email=d["email"], address=d["address"], intro=d["intro"], lines=d["lines"], terms=d["terms"],
                           issued=business_today(), due=date.fromisoformat(d["due_date"]) if d.get("due_date") else None,
                           paid=d["opening_paid"], payments=payments, invoice=True, bank=profile.bank_details)
        return Response(content, media_type="application/pdf", headers={"Content-Disposition":"inline; filename=ivory-invoice-preview.pdf", "Cache-Control":"no-store"})

    @app.get("/api/ivory-quotes/{offer_id}/pdf")
    def pdf(offer_id: str, _: Admin = Depends(current_admin), db=Depends(get_db)):
        row = get(db, offer_id)
        return Response(offer_pdf(row.contents, profile_for(db), f"IDQ-{row.group_id[:8].upper()}-R{row.revision}"), media_type="application/pdf",
                        headers={"Content-Disposition":"inline; filename=ivory-quote.pdf", "Cache-Control":"no-store"})

    @app.get("/ivory-quote/{token}", include_in_schema=False)
    def public_page(token: str):
        return FileResponse(Path(__file__).parent / "static" / "ivory-quote.html", headers={"Cache-Control":"no-store"})

    @app.get("/api/public/ivory-quotes/{token}")
    def public_data(token: str, db=Depends(get_db)):
        row = public(db, token)
        result = offer_json(db, row)
        # Opening payments are deliberately visible to the recipient for checking.
        result.pop("booking_id"); result.pop("acceptance")
        return result

    @app.post("/api/public/ivory-quotes/{token}/accept")
    def public_accept(token: str, payload: Agreement, db=Depends(get_db)):
        row = public(db, token, True)
        if row.status == "accepted":
            existing = db.get(Invoice, row.invoice_id) if row.invoice_id else None
            return {"ok":True, "number":existing.number if existing else None}
        invoice = accept_services(db, row)
        row.status = "accepted"; row.accepted_at = now()
        row.acceptance = {"method":"client", "name":payload.name, "accepted_at":row.accepted_at.isoformat()}
        audit(db, "ivory_quote_accepted", "booking", row.booking_id, {"offer_id":row.id, "name":payload.name})
        db.commit()
        return {"ok":True, "number":invoice.number if invoice else None}

    @app.get("/api/public/ivory-quotes/{token}/invoice.pdf")
    def public_invoice(token: str, db=Depends(get_db)):
        row = public(db, token)
        data = offer_json(db, row)
        if row.status != "accepted" or not data["invoice"]:
            raise HTTPException(404, "Accept the quote before viewing its invoice.")
        from .pdf import invoice_pdf
        invoice = db.get(Invoice, data["invoice"]["id"])
        return Response(invoice_pdf(invoice, profile_for(db)), media_type="application/pdf",
                        headers={"Content-Disposition":f'inline; filename="{invoice.number}.pdf"', "Cache-Control":"no-store"})

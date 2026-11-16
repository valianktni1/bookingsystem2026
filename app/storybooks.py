"""Personalised book enquiries and standalone WBM sales."""
import hashlib
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator
from sqlalchemy import DateTime, ForeignKey, String, or_, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload
from sqlalchemy.types import JSON

from .business_time import business_today
from .config import get_settings
from .database import Base, get_db
from .enquiry_delivery import enqueue_enquiry_message
from .models import Admin, Booking, Brand, BusinessProfile, Client, Invoice, RecordKind, RecordStatus, SystemSetting, now, uid
from .quote_templates import booking_bank_details
from .security import current_admin
from .services import audit, next_invoice_number
from .storybook_form import KEY as FORM_KEY, THEMES, QuestionKey, SavedAnswer, StorybookForm, ThemeKey, collect_answers, get_form

UNIT_PRICE = Decimal("34.99")
SOURCE = "storybook_order"
OWNER_KEY = "new_storybook_admin"
WEDDING_THEMES = {"wedding", "christmas_wedding"}
Text80 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Text160 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Text600 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
Text1000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class StorybookOrder(Base):
    __tablename__ = "storybook_orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_key: Mapped[str] = mapped_column(String(64), unique=True)
    billing_id: Mapped[str] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), unique=True)
    wedding_id: Mapped[str | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"), index=True)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), unique=True)
    details: Mapped[dict] = mapped_column(JSON)
    delivery: Mapped[dict] = mapped_column(JSON, default=dict)
    fulfilment: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    billing: Mapped[Booking] = relationship(foreign_keys=[billing_id])
    invoice: Mapped[Invoice | None] = relationship(foreign_keys=[invoice_id])


class BookCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Text80
    role: Literal["flower_girl", "pageboy", "child"]
    hair: Literal["black", "dark_brown", "light_brown", "blonde", "red_ginger", "other"]
    hair_other: Text80 | None = None
    dedication: Text600 | None = None
    quantity: int = Field(default=1, ge=1, le=24)

    @model_validator(mode="after")
    def require_other_hair(self):
        if self.hair == "other" and not self.hair_other:
            raise ValueError("Enter the hair colour when you choose Other.")
        if self.hair != "other":
            self.hair_other = None
        return self


class BookDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: ThemeKey = "wedding"
    theme_title: Text160 | None = None
    custom_answers: list[SavedAnswer] = Field(default_factory=list, max_length=20)
    wedding_date: date | None = None
    ceremony: Literal["one_venue", "church_separate", "other"] | None = None
    venue: Text160 | None = None
    destination: Text160 | None = None
    separate_venues: bool = False
    reception: Text160 | None = None
    needed_by: date | None = None
    gift: bool = False
    books: list[BookCopy] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def check_order(self):
        if self.theme in WEDDING_THEMES:
            if not (self.wedding_date and self.venue and self.ceremony):
                raise ValueError("Enter the wedding date, ceremony type and venue.")
            if any(book.role == "child" for book in self.books):
                raise ValueError("Choose flower girl or pageboy for each wedding book.")
            if self.ceremony == "church_separate":
                self.separate_venues = True
            elif self.ceremony == "one_venue":
                self.separate_venues = False
            if self.separate_venues and not self.reception:
                raise ValueError("Enter the reception venue as well as the ceremony venue.")
        else:
            self.wedding_date = self.ceremony = self.venue = None
            self.separate_venues = False
            for book in self.books:
                book.role = "child"
        if not self.separate_venues:
            self.reception = None
        if self.theme != "holiday":
            self.destination = None
        if sum(book.quantity for book in self.books) > 24:
            raise ValueError("Please request up to 24 copies per order.")
        return self


class RequestDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_id: UUID
    details: BookDetails
    privacy_agreed: Literal[True]
    website: str = Field(default="", max_length=500)


class PublicRequest(RequestDetails):
    form_revision: str | None = Field(default=None, max_length=64)
    answers: dict[QuestionKey, Annotated[str, StringConstraints(max_length=1000)]] = Field(default_factory=dict, max_length=20)
    buyer_name: Text160
    buyer_email: EmailStr


class OrderEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    buyer_name: Text160
    buyer_email: EmailStr
    billing_address: Text1000 | None = None
    delivery_name: Text160 | None = None
    delivery_address: Text1000 | None = None
    details: BookDetails


class InvoiceRequest(BaseModel):
    due_date: date
    unit_price: Decimal | None = Field(default=None, gt=0, le=10000, decimal_places=2)


class FulfilmentRequest(BaseModel):
    stage: Literal["sent_to_print", "dispatched", "cancelled"]


_hits = OrderedDict()
_hit_lock = Lock()


def rate_limit(request):
    address = request.client.host if request.client else "unknown"
    timestamp = monotonic()
    with _hit_lock:
        while _hits and next(iter(_hits.values()))[-1] <= timestamp - 3600:
            _hits.popitem(last=False)
        times = [t for t in _hits.get(address, []) if t > timestamp - 3600]
        if len(times) >= 15:
            raise HTTPException(429, "Too many storybook requests. Please try again later.")
        _hits[address] = times + [timestamp]
        # Entries are ordered by the most recent hit, so expire only whole entries.
        _hits.move_to_end(address)
        while len(_hits) > 4096:
            _hits.popitem(last=False)


def available_wedding(booking):
    return (booking.brand == Brand.WBM and booking.kind == RecordKind.WEDDING
            and not booking.archived_at and booking.status != RecordStatus.CANCELLED)


def is_storybook_sale(booking):
    return bool(booking and (booking.workflow_state or {}).get("source") == SOURCE)


def new_storybook_count(db):
    return db.scalar(select(func.count()).select_from(StorybookOrder)
                     .outerjoin(Invoice, Invoice.id == StorybookOrder.invoice_id)
                     .where(StorybookOrder.fulfilment == "open",
                            or_(Invoice.id.is_(None), Invoice.status.in_(("void", "cancelled")))))


def couple_can_see_invoice(order, booking):
    return invoice_open(order.invoice) and order.billing.client.email.lower() == booking.client.email.lower()


def quantity(details):
    return sum(item["quantity"] for item in details["books"])


def invoice_open(invoice):
    return bool(invoice and invoice.status not in ("void", "cancelled"))


def stage(order):
    if order.fulfilment != "open":
        return order.fulfilment
    invoice = order.invoice
    if not invoice_open(invoice):
        return "new"
    return "paid" if invoice.paid >= invoice.total else "invoiced"


def order_json(order):
    invoice = order.invoice
    buyer = order.billing.client
    theme = order.details.get("theme", "wedding")
    total = invoice.total if invoice_open(invoice) else UNIT_PRICE * quantity(order.details) if theme == "wedding" else None
    return {
        "id": order.id, "wedding_id": order.wedding_id,
        "billing_id": order.billing_id,
        "buyer_name": " ".join(filter(None, (buyer.first_name, buyer.last_name))),
        "buyer_email": buyer.email, "billing_address": buyer.address,
        "details": order.details, "delivery": order.delivery,
        "quantity": quantity(order.details), "total": float(total) if total is not None else None,
        "stage": stage(order), "created_at": order.created_at.isoformat(),
        "invoice": ({"id": invoice.id, "number": invoice.number, "paid": float(invoice.paid),
                     "total": float(invoice.total), "status": invoice.status,
                     "balance": float(invoice.total - invoice.paid)} if invoice else None),
    }


def new_order(db, payload, request, *, wedding=None, buyer_name, buyer_email, test_mode):
    key = hashlib.sha256(f"{wedding.id if wedding else 'public'}:{payload.submission_id}".encode()).hexdigest()
    if payload.website or db.scalar(select(StorybookOrder.id).where(StorybookOrder.request_key == key)):
        return {"ok": True}
    if isinstance(payload, PublicRequest):
        form = get_form(db)
        if payload.form_revision != form.revision() and (payload.form_revision is not None or db.get(SystemSetting, FORM_KEY)):
            raise HTTPException(409, "The storybook form has changed. Please reopen it before sending your request.")
        story = next((story for story in form.stories if story.id == payload.details.theme and story.enabled), None)
        if story is None:
            raise HTTPException(422, "Choose one of the available stories.")
        payload.details.theme_title = story.label
        payload.details.custom_answers = collect_answers(form, story.id, payload.answers)
    else:
        if payload.details.theme not in THEMES:
            raise HTTPException(422, "Choose one of the stories available in your wedding portal.")
        payload.details.theme_title = None
        payload.details.custom_answers = []
    rate_limit(request)
    first, _, last = buyer_name.partition(" ")
    client = Client(first_name=first[:100], last_name=(first[100:] + " " + last).strip()[:100],
                    email=str(buyer_email).lower())
    db.add(client)
    db.flush()
    mode = test_mode(db)
    is_test = wedding.is_test if wedding else mode["enabled"]
    state = {"source": SOURCE}
    if is_test:
        state["test_email"] = ((wedding.workflow_state or {}).get("test_email") if wedding else None) or mode["email"]
    billing = Booking(brand=Brand.WBM, kind=RecordKind.DIGITAL, status=RecordStatus.IN_PROGRESS,
                      title=buyer_name, client_id=client.id, is_test=is_test,
                      workflow_state=state)
    db.add(billing)
    try:
        db.flush()
        order = StorybookOrder(billing_id=billing.id, wedding_id=wedding.id if wedding else None,
                               request_key=key, details=payload.details.model_dump(mode="json"))
        db.add(order)
        db.flush()
        audit(db, "storybook_requested", "booking", billing.id, {"storybook_id": order.id})
        settings = get_settings()
        enqueue_enquiry_message(
            db, billing, OWNER_KEY, recipient=state.get("test_email") or settings.admin_email,
            subject=f"New storybook request · {payload.details.theme_title or THEMES[payload.details.theme]}",
            body=(f"A new storybook request for {quantity(order.details)} book(s) is ready to review.\n\n"
                  f"Open Storybooks in your booking app: {settings.app_url.rstrip('/')}/storybooks"),
            reply_to=state.get("test_email") or client.email,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        if not db.scalar(select(StorybookOrder.id).where(StorybookOrder.request_key == key)):
            raise
    return {"ok": True}


def register_storybook_routes(app, *, resolve_portal, testing_mode, full_invoice, invoice_json, public_pdf):
    @app.get("/storybook-order", include_in_schema=False)
    def public_page():
        return FileResponse(Path(__file__).parent / "static" / "storybook.html",
                            headers={"Cache-Control": "no-store"})

    def form_response(form):
        return {"config": form.model_dump(mode="json"), "revision": form.revision()}

    @app.get("/api/public/storybooks/form")
    def public_form(response: Response, db=Depends(get_db)):
        form = get_form(db)
        response.headers["Cache-Control"] = "no-store"
        result = form_response(form)
        result["config"]["stories"] = [story for story in result["config"]["stories"] if story["enabled"]]
        visible = {story["id"] for story in result["config"]["stories"]}
        result["config"]["questions"] = [q for q in result["config"]["questions"] if q["story"] is None or q["story"] in visible]
        return result

    @app.get("/api/storybooks/form")
    def admin_form(response: Response, _: Admin = Depends(current_admin), db=Depends(get_db)):
        response.headers["Cache-Control"] = "no-store"
        return form_response(get_form(db))

    @app.put("/api/storybooks/form")
    def save_form(payload: StorybookForm, _: Admin = Depends(current_admin), db=Depends(get_db)):
        row = db.get(SystemSetting, FORM_KEY)
        if row is None:
            row = SystemSetting(key=FORM_KEY)
            db.add(row)
        row.value = payload.model_dump(mode="json")
        db.commit()
        return form_response(payload)

    @app.post("/api/public/storybooks", status_code=201)
    def public_order(payload: PublicRequest, request: Request, db=Depends(get_db)):
        return new_order(db, payload, request, buyer_name=payload.buyer_name,
                         buyer_email=payload.buyer_email, test_mode=testing_mode)

    def wedding_for(db, token):
        booking = resolve_portal(db, token).booking
        if not available_wedding(booking):
            raise HTTPException(404, "Storybooks are available for Weddings By Mark couples.")
        return booking

    @app.post("/api/client/{token}/storybooks", status_code=201)
    def couple_order(token: str, payload: RequestDetails, request: Request, db=Depends(get_db)):
        booking = wedding_for(db, token)
        client = booking.client
        return new_order(db, payload, request, wedding=booking,
                         buyer_name=" ".join(filter(None, (client.first_name, client.last_name))),
                         buyer_email=client.email, test_mode=testing_mode)

    @app.get("/api/client/{token}/storybooks")
    def couple_orders(token: str, db=Depends(get_db)):
        booking = wedding_for(db, token)
        rows = db.scalars(select(StorybookOrder).where(StorybookOrder.wedding_id == booking.id)
                          .order_by(StorybookOrder.created_at.desc())).all()
        return [{"quantity": quantity(row.details), "stage": stage(row),
                 "invoice_id": row.invoice_id if couple_can_see_invoice(row, booking) else None,
                 "paid": float(row.invoice.paid) if couple_can_see_invoice(row, booking) else 0} for row in rows]

    @app.get("/api/client/{token}/storybooks/invoices/{invoice_id}/{document}")
    def couple_invoice(token: str, invoice_id: str, document: Literal["invoice.pdf", "receipt.pdf"], db=Depends(get_db)):
        booking = wedding_for(db, token)
        order = db.scalar(select(StorybookOrder).where(StorybookOrder.wedding_id == booking.id,
                                                      StorybookOrder.invoice_id == invoice_id))
        if not order or not couple_can_see_invoice(order, booking):
            raise HTTPException(404, "Storybook invoice not found")
        return public_pdf(db, invoice_id, document == "receipt.pdf")

    @app.get("/api/storybooks")
    def orders(wedding_id: str | None = None, offset: int = 0, _: Admin = Depends(current_admin), db=Depends(get_db)):
        query = select(StorybookOrder).options(
            selectinload(StorybookOrder.billing).selectinload(Booking.client),
            selectinload(StorybookOrder.invoice),
        )
        if wedding_id:
            query = query.where(StorybookOrder.wedding_id == wedding_id)
        return [order_json(row) for row in db.scalars(query.order_by(StorybookOrder.created_at.desc(), StorybookOrder.id)
                                                       .offset(max(0, offset)).limit(51))]

    def get_order(db, order_id):
        row = db.scalar(select(StorybookOrder).where(StorybookOrder.id == order_id).with_for_update())
        if not row:
            raise HTTPException(404, "Storybook request not found")
        return row

    @app.patch("/api/storybooks/{order_id}")
    def edit(order_id: str, payload: OrderEdit, _: Admin = Depends(current_admin), db=Depends(get_db)):
        row = get_order(db, order_id)
        if row.fulfilment in ("dispatched", "cancelled"):
            raise HTTPException(409, "This order has been dispatched or cancelled.")
        previous = BookDetails.model_validate(row.details)
        if payload.details.theme != previous.theme and payload.details.theme not in THEMES:
            raise HTTPException(422, "Choose an available story.")
        payload.details.theme_title = previous.theme_title if payload.details.theme == previous.theme else None
        payload.details.custom_answers = previous.custom_answers
        details = payload.details.model_dump(mode="json")
        if row.fulfilment == "sent_to_print" and details != previous.model_dump(mode="json"):
            raise HTTPException(409, "The book details are frozen after printing. You can still update delivery.")

        if invoice_open(row.invoice) and (quantity(details) != quantity(row.details) or
                                          details["theme"] != row.details.get("theme", "wedding")):
            raise HTTPException(409, "Close the invoice before changing the theme or number of copies.")
        buyer = row.billing.client
        if invoice_open(row.invoice) and (payload.buyer_name != " ".join(filter(None, (buyer.first_name, buyer.last_name)))
                                        or payload.buyer_email != buyer.email or payload.billing_address != buyer.address):
            raise HTTPException(409, "The bill-to details are fixed on the issued invoice.")
        name, _, surname = payload.buyer_name.partition(" ")
        buyer.first_name = name[:100]
        buyer.last_name = (name[100:] + " " + surname).strip()[:100]
        buyer.email = str(payload.buyer_email).lower()
        buyer.address = payload.billing_address
        row.billing.title = payload.buyer_name
        row.details = details
        row.delivery = {"name": payload.delivery_name, "address": payload.delivery_address}
        db.commit()
        return order_json(row)

    @app.post("/api/storybooks/{order_id}/invoice", status_code=201)
    def create_invoice(order_id: str, payload: InvoiceRequest, _: Admin = Depends(current_admin), db=Depends(get_db)):
        row = get_order(db, order_id)
        if row.fulfilment != "open":
            raise HTTPException(409, "This storybook request is closed.")
        if invoice_open(row.invoice):
            return invoice_json(full_invoice(db, row.invoice_id))
        if row.invoice and row.invoice.paid > 0:
            raise HTTPException(409, "Resolve payments on the previous invoice before reissuing.")
        today = business_today()
        if payload.due_date < today:
            raise HTTPException(422, "Choose a due date on or after today.")
        qty = quantity(row.details)
        theme = row.details.get("theme", "wedding")
        unit = UNIT_PRICE if theme == "wedding" else payload.unit_price
        if unit is None:
            raise HTTPException(422, "Enter the agreed price per book before invoicing.")
        title = row.details.get("theme_title") or THEMES.get(theme, "Storybook")
        name = f"Personalised {title} (hardback)"
        total = unit * qty
        seq, number = next_invoice_number(db, Brand.WBM)
        invoice = Invoice(booking_id=row.billing_id, brand=Brand.WBM, sequence=seq, number=number,
                          issue_date=today, due_date=payload.due_date, total=total, paid=Decimal("0"),
                          status="unpaid", description=name,
                          line_items=[{"type": "addon", "code": "personalised_wedding_storybook",
                                       "name": name, "description": f"{qty} × £{unit:.2f} each · UK delivery included",
                                       "quantity": qty, "unit_price": float(unit), "total": float(total)}])
        db.add(invoice)
        db.flush()
        profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == Brand.WBM))
        wedding = db.get(Booking, row.wedding_id) if row.wedding_id else None
        wf = row.billing.workflow_state or {}
        row.billing.workflow_state = {**wf, "invoice_bank_details": {
            **wf.get("invoice_bank_details", {}), invoice.id: dict(booking_bank_details(wedding, profile))}}
        row.invoice_id = invoice.id
        audit(db, "create_invoice", "booking", row.billing_id, {"number": number, "storybook_id": row.id})
        db.commit()
        return invoice_json(full_invoice(db, invoice.id))

    @app.post("/api/storybooks/{order_id}/fulfilment")
    def fulfil(order_id: str, payload: FulfilmentRequest, _: Admin = Depends(current_admin), db=Depends(get_db)):
        row = get_order(db, order_id)
        if row.fulfilment == payload.stage:
            return order_json(row)
        allowed = {"open": ("sent_to_print", "cancelled"), "sent_to_print": ("dispatched",)}
        if payload.stage not in allowed.get(row.fulfilment, ()):
            raise HTTPException(409, "This change is not valid at the current order stage.")
        invoice = full_invoice(db, row.invoice_id, for_update=True) if row.invoice_id else None
        if payload.stage == "cancelled" and invoice_open(invoice):
            raise HTTPException(409, "Close the invoice through Payments & invoices first.")
        if payload.stage != "cancelled":
            if not invoice_open(invoice) or invoice.paid < invoice.total:
                raise HTTPException(409, "Record full payment before printing or dispatching.")
            if not row.delivery.get("name") or not row.delivery.get("address"):
                raise HTTPException(409, "Save the delivery recipient and UK address first.")
        row.fulfilment = payload.stage
        audit(db, "storybook_" + payload.stage, "booking", row.billing_id, {"storybook_id": row.id})
        db.commit()
        return order_json(row)

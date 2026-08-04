from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import Brand, RecordKind, RecordStatus


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ClientIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    partner_name: str | None = Field(default=None, max_length=160)
    company_name: str | None = Field(default=None, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None


class ClientPatch(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    partner_name: str | None = Field(default=None, max_length=160)
    company_name: str | None = Field(default=None, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None


class BookingIn(BaseModel):
    brand: Brand
    kind: RecordKind
    status: RecordStatus = RecordStatus.ENQUIRY
    title: str = Field(min_length=1, max_length=200)
    client: ClientIn
    event_date: date | None = None
    venue_or_project: str | None = Field(default=None, max_length=240)
    venue_address: str | None = Field(default=None, max_length=1000)
    venue_place_id: str | None = Field(default=None, max_length=255)
    venue_lat: float | None = Field(default=None, ge=-90, le=90)
    venue_lng: float | None = Field(default=None, ge=-180, le=180)
    package_name: str | None = Field(default=None, max_length=160)
    quoted_total: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_paid_date: date | None = None
    balance_due_date: date | None = None
    notes: str | None = None


class BookingPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: RecordStatus | None = None
    event_date: date | None = None
    venue_or_project: str | None = None
    venue_address: str | None = Field(default=None, max_length=1000)
    venue_place_id: str | None = Field(default=None, max_length=255)
    venue_lat: float | None = Field(default=None, ge=-90, le=90)
    venue_lng: float | None = Field(default=None, ge=-180, le=180)
    package_name: str | None = None
    quoted_total: Decimal | None = Field(default=None, ge=0)
    deposit_amount: Decimal | None = Field(default=None, ge=0)
    deposit_paid_date: date | None = None
    balance_due_date: date | None = None
    notes: str | None = None
    form_data: dict | None = None
    workflow_state: dict | None = None
    client: ClientPatch | None = None


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    due_at: datetime | None = None
    workflow_key: str | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    due_at: datetime | None = None
    completed: bool | None = None


class InvoiceIn(BaseModel):
    total: Decimal = Field(gt=0)
    issue_date: date = Field(default_factory=date.today)
    deposit_due_date: date | None = None
    supply_date: date | None = None
    due_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)
    paid: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_date: date = Field(default_factory=date.today)
    payment_type: str = Field(default="bank_transfer", max_length=40)
    reference: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class BusinessPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    legal_name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=200)
    address: str | None = None
    bank_details: dict | None = None


class EmailTemplatePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=140)
    subject: str | None = Field(default=None, min_length=1, max_length=240)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    is_active: bool | None = None


class ContractTemplatePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    version: str | None = Field(default=None, min_length=1, max_length=60)
    body: str | None = Field(default=None, min_length=1, max_length=50000)
    is_active: bool | None = None


class PortalCreateIn(BaseModel):
    expires_days: int = Field(default=90, ge=1, le=365)


class PublicFormIn(BaseModel):
    form_type: str = Field(pattern="^(booking_form|final_questionnaire)$")
    data: dict


class ContractAcceptIn(BaseModel):
    accepted_name: str = Field(min_length=2, max_length=180)
    accepted_email: EmailStr
    agreed: bool


class SendEmailIn(BaseModel):
    template_key: str = Field(min_length=2, max_length=80)
    portal_url: str | None = Field(default=None, max_length=1000)


class TemplateTestIn(BaseModel):
    recipient: EmailStr


class PackageOptionIn(BaseModel):
    code: str = Field(pattern="^[a-z0-9_-]{2,80}$")
    name: str = Field(min_length=2, max_length=180)
    description: str = Field(min_length=2, max_length=20000)
    price: Decimal = Field(ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    display_order: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class PackageOptionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, min_length=2, max_length=20000)
    price: Decimal | None = Field(default=None, ge=0)
    deposit_amount: Decimal | None = Field(default=None, ge=0)
    display_order: int | None = Field(default=None, ge=0, le=1000)
    is_active: bool | None = None


class AddOnOptionIn(BaseModel):
    code: str = Field(pattern="^[a-z0-9_-]{2,80}$")
    name: str = Field(min_length=2, max_length=180)
    description: str = Field(min_length=2, max_length=10000)
    price: Decimal = Field(ge=0)
    eligible_package_codes: list[str] = Field(default_factory=list, max_length=100)
    display_order: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class AddOnOptionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, min_length=2, max_length=10000)
    price: Decimal | None = Field(default=None, ge=0)
    eligible_package_codes: list[str] | None = Field(default=None, max_length=100)
    display_order: int | None = Field(default=None, ge=0, le=1000)
    is_active: bool | None = None


class QuoteAcceptIn(BaseModel):
    package_id: str = Field(min_length=36, max_length=36)
    addon_ids: list[str] = Field(default_factory=list, max_length=50)
    confirmed: bool


class EnquiryIn(BaseModel):
    primary_first_name: str = Field(min_length=1, max_length=100)
    partner_first_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    event_date: date
    location: str = Field(min_length=2, max_length=240)
    venue_address: str | None = Field(default=None, max_length=1000)
    venue_place_id: str | None = Field(default=None, max_length=255)
    venue_lat: float | None = Field(default=None, ge=-90, le=90)
    venue_lng: float | None = Field(default=None, ge=-180, le=180)
    package_interest: str | None = Field(default=None, max_length=180)
    selfie_booth_interest: str | None = Field(default=None, max_length=30)
    message: str | None = Field(default=None, max_length=5000)
    promo_code: str | None = Field(default=None, max_length=80)
    heard_about_us: str = Field(min_length=1, max_length=120)
    fun_answer: str | None = Field(default=None, max_length=200)
    privacy_agreed: bool
    website: str | None = Field(default=None, max_length=500)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

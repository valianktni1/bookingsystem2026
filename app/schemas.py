from datetime import date, datetime
from decimal import Decimal
from typing import Literal

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


class FinalCallPackIn(BaseModel):
    checklist: dict[str, bool] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=10000)
    completed: bool = False


class InvoiceIn(BaseModel):
    total: Decimal = Field(gt=0)
    issue_date: date = Field(default_factory=date.today)
    deposit_due_date: date | None = None
    supply_date: date | None = None
    due_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)
    paid: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class InvoiceDueDatePatch(BaseModel):
    due_date: date
    reason: str | None = Field(default=None, max_length=500)


class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_date: date = Field(default_factory=date.today)
    payment_type: Literal["bank_transfer", "cash"] = "bank_transfer"
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


class EmailTemplateIn(BaseModel):
    brand: Brand
    template_key: str = Field(pattern="^[a-z0-9_]{2,80}$")
    display_name: str = Field(min_length=1, max_length=140)
    subject: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=20000)
    is_active: bool = True


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
    expires_days: int = Field(default=365, ge=1, le=3650)
    manual_confirmation: str | None = Field(default=None, max_length=100)
    manual_reason: str | None = Field(default=None, max_length=1000)


class PublicFormIn(BaseModel):
    form_type: str = Field(pattern="^(booking_form|final_timings)$")
    data: dict


class ContractAcceptIn(BaseModel):
    accepted_name: str = Field(min_length=2, max_length=180)
    accepted_email: EmailStr
    agreed: bool


class SendEmailIn(BaseModel):
    template_key: str = Field(min_length=2, max_length=80)
    portal_url: str | None = Field(default=None, max_length=1000)
    manual_confirmation: str | None = Field(default=None, max_length=100)
    manual_reason: str | None = Field(default=None, max_length=1000)


class ClientEmailComposeIn(BaseModel):
    mode: Literal["template", "manual"]
    template_key: str | None = Field(default=None, min_length=2, max_length=80)
    subject: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=20000)
    manual_confirmation: str | None = Field(default=None, max_length=100)
    manual_reason: str | None = Field(default=None, max_length=1000)


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
    is_discount: bool = False


class AddOnOptionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, min_length=2, max_length=10000)
    price: Decimal | None = Field(default=None, ge=0)
    eligible_package_codes: list[str] | None = Field(default=None, max_length=100)
    display_order: int | None = Field(default=None, ge=0, le=1000)
    is_active: bool | None = None
    is_discount: bool | None = None


class QuotePreparationItemIn(BaseModel):
    addon_id: str = Field(min_length=36, max_length=36)
    price: Decimal = Field(ge=0, le=100000)


class QuotePreparationIn(BaseModel):
    required_addons: list[QuotePreparationItemIn] = Field(default_factory=list, max_length=50)
    discounts: list[QuotePreparationItemIn] = Field(default_factory=list, max_length=20)


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
    custom_answers: dict[str, str | bool | list[str] | None] = Field(default_factory=dict)


class EnquiryFormFieldIn(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=240)
    field_type: str = Field(pattern=r"^(text|email|tel|date|select|textarea|checkbox|venue|package)$")
    placeholder: str = Field(default="", max_length=240)
    help_text: str = Field(default="", max_length=500)
    required: bool = False
    enabled: bool = True
    width: str = Field(default="full", pattern=r"^(half|full)$")
    options: list[str] = Field(default_factory=list, max_length=100)
    custom: bool = False


class EnquiryFormTemplateIn(BaseModel):
    heading: str = Field(min_length=1, max_length=300)
    introduction: str = Field(default="", max_length=1000)
    payment_title: str = Field(default="", max_length=200)
    payment_options: list[str] = Field(default_factory=list, max_length=10)
    fields: list[EnquiryFormFieldIn] = Field(min_length=1, max_length=80)
    submit_label: str = Field(default="Submit enquiry", min_length=1, max_length=80)
    success_heading: str = Field(default="Thank you!", min_length=1, max_length=200)
    success_message: str = Field(default="Your enquiry has landed safely.", min_length=1, max_length=1000)


class BookingFormStepIn(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    introduction: str = Field(default="", max_length=500)


class BookingFormFieldIn(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=240)
    field_type: str = Field(pattern=r"^(text|email|tel|date|time|number|select|textarea|venue|package|payment_plan)$")
    step: str = Field(min_length=1, max_length=80)
    placeholder: str = Field(default="", max_length=240)
    help_text: str = Field(default="", max_length=500)
    required: bool = False
    enabled: bool = True
    width: str = Field(default="full", pattern=r"^(half|full)$")
    options: list[str] = Field(default_factory=list, max_length=100)
    custom: bool = False


class PaymentPlanTemplateIn(BaseModel):
    code: str = Field(pattern=r"^(standard|split|quarter)$")
    label: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=500)


class BookingFormTemplateIn(BaseModel):
    heading: str = Field(min_length=1, max_length=300)
    introduction: str = Field(default="", max_length=1000)
    submit_label: str = Field(default="Submit Wedding Booking Form", min_length=1, max_length=100)
    success_message: str = Field(default="Thank you. Your answers have been securely added to your wedding file and are now available to Mark.", min_length=1, max_length=1000)
    steps: list[BookingFormStepIn] = Field(min_length=1, max_length=10)
    payment_plans: list[PaymentPlanTemplateIn] = Field(min_length=3, max_length=3)
    fields: list[BookingFormFieldIn] = Field(min_length=1, max_length=100)


class TestingModeIn(BaseModel):
    enabled: bool
    email: EmailStr


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

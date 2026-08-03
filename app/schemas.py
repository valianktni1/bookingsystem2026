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


class BookingIn(BaseModel):
    brand: Brand
    kind: RecordKind
    status: RecordStatus = RecordStatus.ENQUIRY
    title: str = Field(min_length=1, max_length=200)
    client: ClientIn
    event_date: date | None = None
    venue_or_project: str | None = Field(default=None, max_length=240)
    package_name: str | None = Field(default=None, max_length=160)
    quoted_total: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_paid_date: date | None = None
    balance_due_date: date | None = None
    notes: str | None = None


class BookingPatch(BaseModel):
    status: RecordStatus | None = None
    event_date: date | None = None
    venue_or_project: str | None = None
    package_name: str | None = None
    quoted_total: Decimal | None = Field(default=None, ge=0)
    deposit_amount: Decimal | None = Field(default=None, ge=0)
    deposit_paid_date: date | None = None
    balance_due_date: date | None = None
    notes: str | None = None
    form_data: dict | None = None
    workflow_state: dict | None = None


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
    supply_date: date | None = None
    paid: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uid() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Brand(str, enum.Enum):
    WBM = "wbm"
    IVORY = "ivory"


class RecordKind(str, enum.Enum):
    WEDDING = "wedding"
    DIGITAL = "digital"


class RecordStatus(str, enum.Enum):
    ENQUIRY = "enquiry"
    QUOTED = "quoted"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    legal_name: Mapped[str] = mapped_column(String(160), default="Mark Adam Powell")
    invoice_prefix: Mapped[str] = mapped_column(String(10))
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_details: Mapped[dict] = mapped_column(JSON, default=dict)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), default="")
    partner_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), index=True)
    kind: Mapped[RecordKind] = mapped_column(Enum(RecordKind), index=True)
    status: Mapped[RecordStatus] = mapped_column(Enum(RecordStatus), default=RecordStatus.ENQUIRY, index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    venue_or_project: Mapped[str | None] = mapped_column(String(240), nullable=True)
    package_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    quoted_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    deposit_paid_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    balance_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    form_data: Mapped[dict] = mapped_column(JSON, default=dict)
    workflow_state: Mapped[dict] = mapped_column(JSON, default=dict)
    legacy_source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    legacy_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    client: Mapped[Client] = relationship()
    tasks: Mapped[list["Task"]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="booking", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    workflow_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    booking: Mapped[Booking] = relationship(back_populates="tasks")


class InvoiceCounter(Base):
    __tablename__ = "invoice_counters"
    key: Mapped[str] = mapped_column(String(40), primary_key=True, default="global")
    value: Mapped[int] = mapped_column(default=2000)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("number", name="uq_invoice_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), index=True)
    sequence: Mapped[int] = mapped_column(index=True)
    number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    issue_date: Mapped[date] = mapped_column(Date, default=date.today)
    supply_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    paid: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(30), default="unpaid")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    booking: Mapped[Booking] = relationship(back_populates="invoices")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    category: Mapped[str] = mapped_column(String(60))
    original_name: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    booking: Mapped[Booking] = relationship(back_populates="documents")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


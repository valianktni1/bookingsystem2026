import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
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
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(200), nullable=True)
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
    __table_args__ = (UniqueConstraint("legacy_source", "legacy_id", name="uq_booking_legacy_source_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), index=True)
    kind: Mapped[RecordKind] = mapped_column(Enum(RecordKind), index=True)
    status: Mapped[RecordStatus] = mapped_column(Enum(RecordStatus), default=RecordStatus.ENQUIRY, index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    venue_or_project: Mapped[str | None] = mapped_column(String(240), nullable=True)
    venue_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    venue_place_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    venue_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    venue_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
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
    legacy_import_batch: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    automation_suppressed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    client: Mapped[Client] = relationship()
    tasks: Mapped[list["Task"]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    booking_notes: Mapped[list["BookingNote"]] = relationship(back_populates="booking", cascade="all, delete-orphan")
    quotes: Mapped[list["Quote"]] = relationship(back_populates="booking", cascade="all, delete-orphan")


class PackageOption(Base):
    __tablename__ = "package_options"
    __table_args__ = (UniqueConstraint("brand", "code", name="uq_package_option_brand_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    display_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AddOnOption(Base):
    __tablename__ = "addon_options"
    __table_args__ = (UniqueConstraint("brand", "code", name="uq_addon_option_brand_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    eligible_package_codes: Mapped[list] = mapped_column(JSON, default=list)
    is_discount: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    display_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="accepted", index=True)
    package_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    selected_addon_ids: Mapped[list] = mapped_column(JSON, default=list)
    line_items: Mapped[list] = mapped_column(JSON, default=list)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    invoice_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    legacy_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    legacy_source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    booking: Mapped[Booking] = relationship(back_populates="quotes")


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
    deposit_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    supply_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    paid: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(30), default="unpaid")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_items: Mapped[list] = mapped_column(JSON, default=list)
    payment_schedule: Mapped[list] = mapped_column(JSON, default=list)
    legacy_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    legacy_quote_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    legacy_source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    booking: Mapped[Booking] = relationship(back_populates="invoices")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    paid_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    payment_type: Mapped[str] = mapped_column(String(40), default="bank_transfer")
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    legacy_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    invoice: Mapped[Invoice] = relationship(back_populates="payments")


class BookingNote(Base):
    __tablename__ = "booking_notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    booking: Mapped[Booking] = relationship(back_populates="booking_notes")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    category: Mapped[str] = mapped_column(String(60))
    original_name: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int]
    source_system: Mapped[str | None] = mapped_column(String(60), nullable=True)
    legacy_document_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    legacy_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    is_client_visible: Mapped[bool] = mapped_column(Boolean, default=False)
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


class EmailTemplate(Base):
    __tablename__ = "email_templates"
    __table_args__ = (UniqueConstraint("brand", "template_key", name="uq_email_template_brand_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), index=True)
    template_key: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(140))
    subject: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ContractTemplate(Base):
    __tablename__ = "contract_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    version: Mapped[str] = mapped_column(String(60))
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class FormTemplate(Base):
    """Editable public/client form configuration.

    A JSON snapshot keeps the builder flexible without requiring a database
    migration whenever another question type is introduced.
    """

    __tablename__ = "form_templates"
    __table_args__ = (UniqueConstraint("brand", "template_key", name="uq_form_template_brand_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), index=True)
    template_key: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(140))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ClientPortalToken(Base):
    __tablename__ = "client_portal_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    booking: Mapped[Booking] = relationship()


class FormSubmission(Base):
    __tablename__ = "form_submissions"
    __table_args__ = (UniqueConstraint("booking_id", "form_type", name="uq_booking_form_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    form_type: Mapped[str] = mapped_column(String(80), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    submission_source: Mapped[str] = mapped_column(String(60), default="client_portal")
    source_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    booking: Mapped[Booking] = relationship()


class ContractAcceptance(Base):
    __tablename__ = "contract_acceptances"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), unique=True, index=True)
    contract_title: Mapped[str] = mapped_column(String(180))
    contract_version: Mapped[str] = mapped_column(String(60))
    contract_body: Mapped[str] = mapped_column(Text)
    accepted_name: Mapped[str] = mapped_column(String(180))
    accepted_email: Mapped[str] = mapped_column(String(254))
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    acceptance_source: Mapped[str] = mapped_column(String(80), default="client_portal")
    source_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_legacy_import: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    booking: Mapped[Booking] = relationship()


class EmailLog(Base):
    __tablename__ = "email_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    template_key: Mapped[str] = mapped_column(String(80), index=True)
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(30), default="sent", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    booking: Mapped[Booking] = relationship()


class MailboxReply(Base):
    """A durable audit copy of replies sent from the unified admin inbox.

    Incoming email remains on Hostinger and is read live over IMAP. Only a
    reply written by the administrator is retained here, so it remains visible
    against the conversation even if the remote Sent folder is unavailable.
    ``booking_id`` is intentionally not a foreign key: historic mail audit must
    not prevent deletion of an empty test booking.
    """

    __tablename__ = "mailbox_replies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    brand: Mapped[Brand] = mapped_column(Enum(Brand), index=True)
    booking_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    recipient: Mapped[str] = mapped_column(String(254), index=True)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    thread_references: Mapped[str | None] = mapped_column(Text, nullable=True)
    copied_to_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="sent", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class ReminderLog(Base):
    __tablename__ = "reminder_logs"
    __table_args__ = (UniqueConstraint("booking_id", "reminder_key", "scheduled_for", name="uq_booking_reminder_day"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    booking_id: Mapped[str] = mapped_column(ForeignKey("bookings.id"), index=True)
    reminder_key: Mapped[str] = mapped_column(String(80), index=True)
    scheduled_for: Mapped[date] = mapped_column(Date, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

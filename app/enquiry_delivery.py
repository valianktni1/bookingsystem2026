"""Durable delivery of new website enquiry mail, outside the HTTP request."""
import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .config import get_settings
from .database import Base, SessionLocal
from .email_service import render_template_content, send_rendered_email
from .models import Booking, Brand, BusinessProfile, EmailLog, RecordStatus

logger = logging.getLogger(__name__)
KEYS = ('enquiry_received', 'new_enquiry_admin')


class EnquiryEmailJob(Base):
    __tablename__ = 'enquiry_email_jobs'
    email_id: Mapped[str] = mapped_column(ForeignKey('email_logs.id', ondelete='CASCADE'), primary_key=True)
    open_tracking_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(String(254), nullable=True)


def queue_enquiry_email(db, booking, profile, template, *, recipient,
                        portal_url=None, extra_values=None, reply_to=None):
    """Persist exact wording and destination in the enquiry transaction; no SMTP."""
    if template.template_key not in KEYS:
        raise ValueError('Only website enquiry emails belong in this queue')
    token = secrets.token_urlsafe(32) if template.template_key == 'enquiry_received' else None
    if token and portal_url:
        separator = '&' if '?' in portal_url else '?'
        portal_url = f'{portal_url}{separator}email_access={token}'
    subject, body = render_template_content(booking, profile, template, portal_url, extra_values)
    email = EmailLog(booking_id=booking.id, template_key=template.template_key,
                     recipient=recipient, subject=subject, body=body, status='queued',
                     tracking_token_hash=hashlib.sha256(token.encode()).hexdigest() if token else None)
    db.add(email)
    db.flush()
    db.add(EnquiryEmailJob(email_id=email.id, reply_to=reply_to,
                         open_tracking_url=(f"{get_settings().app_url.rstrip('/')}/api/public/email-open/{token}.gif" if token else None)))
    return email


def deliver_one(email_id):
    with SessionLocal() as db:
        # A committed conditional claim prevents parallel scans from sending twice.
        claim = db.execute(update(EmailLog).where(EmailLog.id == email_id,
                           EmailLog.status == 'queued', EmailLog.template_key.in_(KEYS))
                           .values(status='sending', last_attempt_at=datetime.now(timezone.utc)))
        db.commit()
        if claim.rowcount != 1:
            return
        email = db.get(EmailLog, email_id)
        job = db.get(EnquiryEmailJob, email_id)
        booking = db.get(Booking, email.booking_id)
        try:
            if (not job or not booking or booking.brand != Brand.WBM or booking.legacy_source
                    or (booking.workflow_state or {}).get('source') != 'website_enquiry'
                    or booking.status == RecordStatus.CANCELLED or booking.archived_at):
                raise ValueError('This enquiry is no longer eligible for queued email')
            profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == booking.brand))
            if not profile:
                raise ValueError('Business profile is missing')
            send_rendered_email(booking, profile, email.recipient, email.subject, email.body,
                                open_tracking_url=job.open_tracking_url, reply_to=job.reply_to,
                                template_key=email.template_key)
        except Exception as error:
            # Never replay an uncertain SMTP result automatically. Existing admin
            # communication failures provide deliberate retries of retained wording.
            email.status = 'failed'
            email.error = str(error)[:2000]
        else:
            email.status = 'sent'
            email.sent_at = datetime.now(timezone.utc)
            email.error = None
        db.commit()


def run_queued_enquiry_emails():
    with SessionLocal() as db:
        ids = db.scalars(select(EmailLog.id).join(EnquiryEmailJob, EnquiryEmailJob.email_id == EmailLog.id)
                         .where(EmailLog.status == 'queued', EmailLog.template_key.in_(KEYS))
                         .order_by(EmailLog.sent_at).limit(20)).all()
    for email_id in ids:
        deliver_one(email_id)


async def enquiry_email_loop():
    while True:
        try:
            await asyncio.to_thread(run_queued_enquiry_emails)
        except Exception:
            logger.exception('Website enquiry email queue scan failed')
        await asyncio.sleep(2)

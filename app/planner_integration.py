"""Opt-in, durable WBM complimentary planner invitations. No historical backfill."""
import asyncio
import base64
import hashlib
from datetime import datetime, timedelta, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .security import current_admin
from .config import get_settings
from .database import Base, SessionLocal, get_db
from .models import Admin, Booking, Brand, Client, EmailLog, Invoice, Quote, RecordKind, RecordStatus, SystemSetting

KEY = 'planner_invitation_connection'
URL = 'https://planner.ivorydigital.uk'
DELAY_MINUTES = 30


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class PlannerInvitation(Base):
    __tablename__ = 'planner_invitations'
    booking_id: Mapped[str] = mapped_column(String(36), ForeignKey('bookings.id', ondelete='CASCADE'), primary_key=True)
    receipt_id: Mapped[str] = mapped_column(String(36))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), default='pending', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planner_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


def connection(db):
    row = db.get(SystemSetting, KEY)
    return dict(row.value or {}) if row else {'enabled': False}


def encryptor():
    key = hashlib.sha256(('wbm-planner-connection:' + get_settings().session_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def credential(config):
    try:
        return encryptor().decrypt(config.get('credential', '').encode()).decode()
    except (InvalidToken, ValueError):
        raise ValueError('Save the planner connection key again in Planner invitations.')


def call_planner(config, method, path, payload=None):
    # Fixed origin, TLS verification and no redirects: the credential can only
    # be sent to this dedicated planner, never a URL supplied by a client.
    with httpx.Client(timeout=httpx.Timeout(12, connect=4), follow_redirects=False) as client:
        return client.request(method, URL + path, headers={'Authorization': 'Bearer ' + credential(config)}, json=payload)


def eligible(db, booking):
    if (booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING or booking.legacy_source
            or booking.automation_suppressed or booking.is_test
            or booking.status not in (RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS)):
        return False
    if not db.scalar(select(Quote.id).where(Quote.booking_id == booking.id, Quote.status == 'accepted').limit(1)):
        return False
    paid = sum((row.paid for row in db.scalars(select(Invoice).where(
        Invoice.booking_id == booking.id, Invoice.status.notin_(('void','cancelled'))))), 0)
    return booking.deposit_amount > 0 and paid >= booking.deposit_amount


def invitation_payload(booking):
    client = booking.client
    if not booking.event_date or booking.event_date < utcnow().date():
        raise ValueError('Add a valid future wedding date to this booking.')
    if not client.first_name or not client.partner_name or not client.email:
        raise ValueError('Add both first names and the main email to this booking.')
    return {'booking_id': booking.id, 'first_name': client.first_name.strip(),
            'partner_first_name': client.partner_name.strip(), 'email': client.email.strip().lower(),
            'wedding_date': booking.event_date.isoformat()}


def schedule_new(db, config):
    since = config.get('enabled_since')
    if not since:
        return
    # Only receipts sent after deliberate activation are eligible. Select the
    # newest receipt first; a partial deposit alone never creates a job.
    receipts = db.scalars(select(EmailLog).join(Booking, Booking.id == EmailLog.booking_id)
        .outerjoin(PlannerInvitation, PlannerInvitation.booking_id == Booking.id).where(
        PlannerInvitation.booking_id.is_(None), Booking.brand == Brand.WBM,
        Booking.kind == RecordKind.WEDDING, Booking.legacy_source.is_(None),
        Booking.automation_suppressed.is_(False), Booking.is_test.is_(False),
        Booking.status.in_((RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS)),
        EmailLog.template_key == 'payment_received', EmailLog.planner_deposit_eligible.is_(True),
        EmailLog.status == 'sent', EmailLog.sent_at >= datetime.fromisoformat(since))
        .order_by(EmailLog.sent_at.desc())).all()
    seen = set()
    for receipt in receipts:
        if receipt.booking_id in seen:
            continue
        seen.add(receipt.booking_id)
        if db.get(PlannerInvitation, receipt.booking_id):
            continue
        booking = db.get(Booking, receipt.booking_id)
        if not booking or not eligible(db, booking):
            continue
        due = aware(receipt.sent_at) + timedelta(minutes=DELAY_MINUTES)
        # A unique booking key prevents two application workers making jobs.
        from sqlalchemy.exc import IntegrityError
        try:
            with db.begin_nested():
                db.add(PlannerInvitation(booking_id=booking.id, receipt_id=receipt.id,
                    due_at=due, next_at=due, status='pending', payload={}))
                db.flush()
        except IntegrityError:
            pass
    db.commit()


def process_one(db, booking_id, config, now):
    job = db.get(PlannerInvitation, booking_id)
    if not job:
        return
    available = job.status in ('pending', 'retry', 'queued') and aware(job.next_at) <= now
    stale = job.status == 'sending' and job.claimed_at and aware(job.claimed_at) < now - timedelta(minutes=5)
    if not (available or stale):
        return
    claimed = db.execute(update(PlannerInvitation).where(
        PlannerInvitation.booking_id == booking_id, PlannerInvitation.status == job.status,
        PlannerInvitation.next_at == job.next_at, PlannerInvitation.claimed_at == job.claimed_at,
    ).values(status='sending', claimed_at=now, attempts=PlannerInvitation.attempts + 1))
    db.commit()
    if claimed.rowcount != 1:
        return
    db.expire_all()
    job = db.get(PlannerInvitation, booking_id)
    booking = db.get(Booking, booking_id)
    if not booking or not eligible(db, booking):
        job.status = 'cancelled'; job.error = 'Booking is no longer eligible; nothing further was requested.'
        db.commit(); return
    try:
        if not job.payload:
            job.payload = invitation_payload(booking)
            db.commit()  # stable replay payload survives a lost network response
        else:
            # Changes after the first network attempt require review, never a
            # second account or a silent overwrite of an existing planner.
            if invitation_payload(booking) != job.payload:
                raise ValueError('Booking details changed after the invitation request. Review the planner account.')
        response = call_planner(config, 'GET' if job.planner_id else 'POST',
            '/api/integrations/wbm/invitations/' + booking_id if job.planner_id else '/api/integrations/wbm/invitations',
            None if job.planner_id else job.payload)
        if response.status_code in (400, 401, 403, 409, 422):
            # Do not echo provider response bodies (which can contain secrets).
            raise ValueError({409:'Planner needs a review: an account may already exist, details changed, or the connection is paused.',
                              401:'Planner connection key was rejected; check both apps.'}.get(response.status_code,
                              'Planner rejected the invitation details. Review the booking and connection settings.'))
        if response.status_code not in (200, 201):
            raise RuntimeError('Planner is temporarily unavailable.')
        result = response.json()
        if result.get('booking_id') != booking_id or not result.get('wedding_id'):
            raise RuntimeError('Planner returned an unexpected acknowledgement.')
        job.planner_id = result['wedding_id']
        state = result.get('status')
        if state in ('sent', 'accepted'):
            job.status = state; job.error = None
        elif state in ('queued', 'retry'):
            job.status = 'queued'; job.error = None; job.attempts = 0; job.next_at = now + timedelta(minutes=2)
        else:
            raise ValueError('Planner email needs attention. Check Email & reminders in planner admin, then retry the status check here.')
    except ValueError as exc:
        job.status = 'needs_attention'; job.error = str(exc)[:500]
    except Exception:
        job.status = 'retry' if job.attempts < 12 else 'needs_attention'
        job.error = 'Connection interrupted or planner unavailable. Retrying safely; check the planner before manually inviting.'
        job.next_at = now + timedelta(seconds=min(3600, 60 * 2 ** min(job.attempts, 6)))
    db.commit()


def run_planner_jobs():
    from .planner_timings import run_timings_jobs
    with SessionLocal() as db:
        config = connection(db)
        if config.get('timings_enabled'): run_timings_jobs()
        if not config.get('enabled') or not config.get('credential'):
            return
        schedule_new(db, config)
        now = utcnow()
        ids = db.scalars(select(PlannerInvitation.booking_id).where(
            PlannerInvitation.status.in_(('pending', 'retry', 'queued', 'sending')),
            PlannerInvitation.next_at <= now).order_by(PlannerInvitation.next_at).limit(25)).all()
        for booking_id in ids:
            process_one(db, booking_id, config, now)


async def planner_invitation_loop():
    while True:
        try:
            await asyncio.to_thread(run_planner_jobs)
        except Exception:
            # Never log credentials or couples' personal data.
            import logging
            logging.getLogger(__name__).warning('Planner invitation scan needs attention; next scan will retry.')
        await asyncio.sleep(30)


class ConnectionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool
    key: str | None = Field(default=None, max_length=200)
    timings_enabled: bool | None = None


def register_planner_routes(app):
    @app.get('/api/planner-invitations/settings')
    def get_connection(_: Admin = Depends(current_admin), db=Depends(get_db)):
        config = connection(db)
        return {'enabled': bool(config.get('enabled')), 'key_saved': bool(config.get('credential')),
                'planner_url': URL, 'delay_minutes': DELAY_MINUTES, 'enabled_since': config.get('enabled_since'),
                'timings_enabled':bool(config.get('timings_enabled')), 'timings_fallback_days':21}

    @app.put('/api/planner-invitations/settings')
    def save_connection(payload: ConnectionIn, _: Admin = Depends(current_admin), db=Depends(get_db)):
        config = connection(db)
        value = payload.key.strip() if payload.key else None
        if value:
            if not value.startswith('wbm_planner_') or len(value) < 40:
                raise HTTPException(422, 'Copy the connection key from planner admin → System & security.')
            config['credential'] = encryptor().encrypt(value.encode()).decode()
        if payload.enabled:
            try:
                response = call_planner(config, 'GET', '/api/integrations/wbm/status')
                if response.status_code != 200 or not response.json().get('ready'):
                    raise ValueError()
            except Exception:
                raise HTTPException(422, 'Cannot enable: check the planner connection key, SMTP, terms and privacy notice.')
            if not config.get('enabled'):
                config['enabled_since'] = utcnow().isoformat()
        if payload.timings_enabled is not None:
            if payload.timings_enabled:
                try:
                    response=call_planner(config,'GET','/api/integrations/wbm/status')
                    if response.status_code!=200 or response.json().get('capabilities',{}).get('timings')!=1:
                        raise ValueError()
                except Exception:
                    raise HTTPException(422,'Update the planner first and check the connection before enabling timings.')
            config['timings_enabled']=payload.timings_enabled
        config['enabled'] = payload.enabled
        row = db.get(SystemSetting, KEY)
        if row:
            row.value = config
        else:
            db.add(SystemSetting(key=KEY, value=config))
        db.commit()
        return {'ok': True, 'enabled': payload.enabled}

    @app.get('/api/planner-invitations/jobs')
    def get_jobs(_: Admin = Depends(current_admin), db=Depends(get_db)):
        rows = db.execute(select(PlannerInvitation, Booking.title).join(Booking, Booking.id == PlannerInvitation.booking_id)
                          .order_by(PlannerInvitation.due_at.desc()).limit(100)).all()
        return [{'booking_id': job.booking_id, 'couple': title, 'status': job.status,
                 'due_at': aware(job.due_at).isoformat(), 'error': job.error} for job, title in rows]

    @app.post('/api/planner-invitations/jobs/{booking_id}/retry')
    def retry_job(booking_id: str, _: Admin = Depends(current_admin), db=Depends(get_db)):
        job = db.get(PlannerInvitation, booking_id)
        if not job or job.status not in ('needs_attention', 'retry', 'cancelled'):
            raise HTTPException(409, 'This invitation does not need a retry.')
        booking = db.get(Booking, booking_id)
        if not eligible(db, booking):
            raise HTTPException(409, 'The booking is not eligible for an automatic planner invitation.')
        job.status = 'queued' if job.planner_id else 'pending'
        job.next_at = max(utcnow(), aware(job.due_at)); job.error = None; job.attempts = 0
        db.commit()
        return {'ok': True}


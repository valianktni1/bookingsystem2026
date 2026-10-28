"""Personal WBM gallery connection. Opt-in, new bookings only, durable retries.

No client emails, gallery deletions or automatic overwrites are performed here.
"""
import asyncio
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .config import get_settings
from .database import Base, SessionLocal, get_db
from .models import Admin, AddOnOption, Booking, Brand, Invoice, PackageOption, Quote, RecordKind, RecordStatus, SystemSetting
from .security import current_admin

KEY = 'gallery_connection'
URL = 'https://weddingsbymark.uk'


def utcnow(): return datetime.now(timezone.utc)


def aware(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class GalleryProvision(Base):
    __tablename__ = 'gallery_provisions'
    booking_id: Mapped[str] = mapped_column(String(36), ForeignKey('bookings.id', ondelete='CASCADE'), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default='pending', index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Rule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    configured: bool = False
    photography: bool = False
    video: bool = False
    full_day: bool = False
    selfie_booth: bool = False
    album_mode: str = Field(default='off', pattern='^(off|40|60)$')


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool
    key: str | None = Field(default=None, max_length=200)
    rules: dict[str, Rule] = Field(default_factory=dict, max_length=1000)


def config(db):
    row = db.get(SystemSetting, KEY)
    return dict(row.value or {}) if row else {'enabled':False, 'rules':{}}


def encryptor():
    key = hashlib.sha256(('wbm-gallery-connection:' + get_settings().session_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def call_gallery(settings, method, path, payload=None):
    try:
        key = encryptor().decrypt(settings.get('credential','').encode()).decode()
    except (InvalidToken,ValueError):
        raise ValueError('Save the gallery connection key again.')
    with httpx.Client(timeout=httpx.Timeout(20,connect=4), follow_redirects=False) as client:
        return client.request(method, URL+path, headers={'Authorization':'Bearer '+key}, json=payload)


def accepted(db,b):
    return db.scalar(select(Quote).where(Quote.booking_id==b.id, Quote.status=='accepted').order_by(Quote.created_at.desc()).limit(1))


def eligible(db,b):
    if not b or b.brand!=Brand.WBM or b.kind!=RecordKind.WEDDING or b.legacy_source or b.automation_suppressed or b.is_test or b.archived_at:
        return False
    if b.status not in (RecordStatus.CONFIRMED,RecordStatus.IN_PROGRESS): return False
    quote = accepted(db,b)
    invoice = db.get(Invoice,quote.invoice_id) if quote and quote.invoice_id else None
    fee = b.deposit_amount
    return bool(invoice and invoice.status not in ('void','cancelled') and fee>0 and invoice.paid>=fee)


def make_payload(db,b,settings):
    q = accepted(db,b)
    if not q: raise ValueError('An accepted quote is required.')
    invoice = db.get(Invoice,q.invoice_id) if q.invoice_id else None
    if not invoice: raise ValueError('The accepted quote invoice is missing.')
    if not b.event_date or b.event_date < utcnow().date(): raise ValueError('A future wedding date is required.')
    c=b.client
    if not c.first_name or not c.partner_name or not c.email: raise ValueError('Both first names and the lead email are required.')
    rules=settings.get('rules',{})
    keys=['package:'+str(q.package_id)]
    # Use the current accepted invoice, including any agreed changes made before creation.
    for line in invoice.line_items or []:
        if line.get('type')=='package': continue
        # A manually entered monetary discount changes price, not deliverables.
        # Catalogue £0 gifts still use their explicit entitlement mapping below.
        if line.get('manual_amendment') and line.get('type')=='discount': continue
        # Zero-price complimentary albums can be stored as discount entries.
        # Their explicit rule is still needed; a price sign never determines entitlement.
        if line.get('type') not in ('addon','discount') or not line.get('code'):
            raise ValueError('An agreed invoice item needs manual gallery review before creation.')
        keys.append('addon:'+line['code'])
    selected=[]
    for key in keys:
        rule=rules.get(key,{})
        if not rule.get('configured'): raise ValueError('Review and save gallery settings for every selected package and extra.')
        selected.append(Rule(**rule))
    modes={r.album_mode for r in selected if r.album_mode!='off'}
    data={'booking_id':b.id,'first_name':c.first_name.strip(),'partner_first_name':c.partner_name.strip(),
        'email':c.email.strip().lower(),'wedding_date':b.event_date.isoformat(),
        **{k:any(getattr(r,k) for r in selected) for k in ('photography','video','full_day','selfie_booth')},
        'album_mode':'60' if '60' in modes else '40' if '40' in modes else 'off'}
    if not any(data[k] for k in ('photography','video','selfie_booth')): raise ValueError('Choose at least one delivery folder for this package.')
    return data


def revision(db,b,settings):
    q=accepted(db,b);i=db.get(Invoice,q.invoice_id) if q and q.invoice_id else None
    source={'quote':q.id if q else None,'invoice':i.id if i else None,'items':i.line_items if i else [],
        'date':str(b.event_date),'names':[b.client.first_name,b.client.partner_name],'email':b.client.email,
        'rules':{k:v for k,v in settings.get('rules',{}).items() if k=='package:'+str(q.package_id if q else '') or k in {'addon:'+str(x.get('code')) for x in (i.line_items or [] if i else [])}},
        'eligible':eligible(db,b)}
    return hashlib.sha256(json.dumps(source,sort_keys=True,default=str).encode()).hexdigest()


def safe_result(data,bid):
    if data.get('booking_id')!=bid or data.get('status')!='created' or not data.get('gallery_id'):
        raise RuntimeError('Unexpected gallery acknowledgement.')
    for key,prefix in [('admin_url','/admin/gallery/'),('guest_url','/s/')]:
        if not data.get(key):
            if key=='admin_url': raise RuntimeError('Gallery link missing.')
            continue
        u=urlparse(data[key])
        if u.scheme!='https' or u.netloc!='weddingsbymark.uk' or not u.path.startswith(prefix) or u.query or u.fragment:
            raise RuntimeError('Unexpected gallery link.')
    return {k:data.get(k) for k in ('booking_id','gallery_id','status','admin_url','guest_url','guest_expires_at')}


def scan(db,settings):
    now=utcnow()
    # Activation boundary is tied to quote acceptance, so existing weddings are never backfilled.
    since=settings.get('enabled_since')
    if not since:return
    quotes=db.scalars(select(Quote).join(Booking,Booking.id==Quote.booking_id).join(Invoice,Invoice.id==Quote.invoice_id)
        .outerjoin(GalleryProvision,GalleryProvision.booking_id==Quote.booking_id).where(
        Quote.status=='accepted',Quote.accepted_at>=datetime.fromisoformat(since),GalleryProvision.booking_id.is_(None),
        Booking.brand==Brand.WBM,Booking.kind==RecordKind.WEDDING,Booking.legacy_source.is_(None),
        Booking.automation_suppressed.is_(False),Booking.is_test.is_(False),Booking.archived_at.is_(None),
        Booking.status.in_((RecordStatus.CONFIRMED,RecordStatus.IN_PROGRESS)),Booking.deposit_amount>0,
        Invoice.status.notin_(('void','cancelled')),Invoice.paid>=Booking.deposit_amount)
        .order_by(Quote.accepted_at).limit(100)).all()
    from sqlalchemy.exc import IntegrityError
    for q in quotes:
        b=db.get(Booking,q.booking_id)
        if not eligible(db,b):continue
        try:
            with db.begin_nested():
                db.add(GalleryProvision(booking_id=b.id,status='pending',next_at=now,payload={},result={}))
                db.flush()
        except IntegrityError:pass
    db.commit()
    for job in db.scalars(select(GalleryProvision).where(GalleryProvision.status.in_(('created','needs_review')))).all():
        b=db.get(Booking,job.booking_id)
        if b and job.status=='created' and revision(db,b,settings)!=job.revision:
            job.status='needs_review';job.error='Booking or package details changed. Review the existing gallery; no gallery content was altered.'
    db.commit()


def process(db,bid,settings):
    now=utcnow();job=db.get(GalleryProvision,bid)
    if not job:return
    ready=job.status in ('pending','retry') and aware(job.next_at)<=now
    stale=job.status=='sending' and job.claimed_at and aware(job.claimed_at)<now-timedelta(minutes=3)
    if not(ready or stale):return
    claimed=db.execute(update(GalleryProvision).where(GalleryProvision.booking_id==bid,
        GalleryProvision.status==job.status,GalleryProvision.claimed_at==job.claimed_at,GalleryProvision.next_at==job.next_at)
        .values(status='sending',claimed_at=now,attempts=GalleryProvision.attempts+1))
    db.commit()
    if claimed.rowcount!=1:return
    db.expire_all();job=db.get(GalleryProvision,bid);b=db.get(Booking,bid)
    try:
        if not eligible(db,b):raise ValueError('This booking is no longer eligible. Nothing was changed in the gallery app.')
        payload=make_payload(db,b,settings)
        current_revision=revision(db,b,settings)
        if job.payload and (payload!=job.payload or current_revision!=job.revision):
            raise ValueError('Booking details changed after a connection attempt. Check the gallery before retrying.')
        if not job.payload:
            job.payload=payload;job.revision=current_revision;db.commit()
        response=call_gallery(settings,'POST','/api/integrations/wbm/galleries',job.payload)
        if response.status_code in (400,401,403,409,422):
            raise ValueError('Gallery setup needs review. Check the connection, matching folder name and package settings; no existing gallery was overwritten.')
        if response.status_code!=200:raise RuntimeError('Gallery unavailable.')
        job.result=safe_result(response.json(),bid);job.status='created';job.error=None
    except ValueError as exc:
        job.status='needs_attention';job.error=str(exc)[:500]
    except Exception:
        job.status='retry' if job.attempts<12 else 'needs_attention'
        job.error='Gallery connection interrupted. The same booking request will be retried without creating duplicates.'
        job.next_at=now+timedelta(seconds=min(3600,60*2**min(job.attempts,6)))
    db.commit()


def run_jobs():
    with SessionLocal() as db:
        settings=config(db)
        if not settings.get('enabled') or not settings.get('credential'):return
        scan(db,settings)
        ids=db.scalars(select(GalleryProvision.booking_id).where(GalleryProvision.status.in_(('pending','retry','sending')),
            GalleryProvision.next_at<=utcnow()).order_by(GalleryProvision.next_at).limit(20)).all()
        for bid in ids:process(db,bid,settings)


async def gallery_loop():
    while True:
        try:await asyncio.to_thread(run_jobs)
        except Exception:
            import logging
            logging.getLogger(__name__).warning('Gallery connection scan needs attention; next scan will retry.')
        await asyncio.sleep(30)


def job_json(job):
    return {'booking_id':job.booking_id,'status':job.status,'error':job.error,'result':job.result or {}}


def register_routes(app):
    @app.get('/api/gallery-connection/settings')
    def get_settings_route(_:Admin=Depends(current_admin),db=Depends(get_db)):
        s=config(db)
        packages=db.scalars(select(PackageOption).where(PackageOption.brand==Brand.WBM).order_by(PackageOption.display_order)).all()
        addons=db.scalars(select(AddOnOption).where(AddOnOption.brand==Brand.WBM).order_by(AddOnOption.display_order)).all()
        items=[{'key':'package:'+p.id,'name':p.name,'kind':'Package','active':p.is_active} for p in packages]+[
            {'key':'addon:'+p.code,'name':p.name,'kind':'Adjustment' if p.is_discount else 'Extra','active':p.is_active} for p in addons]
        return {'enabled':bool(s.get('enabled')),'key_saved':bool(s.get('credential')),'enabled_since':s.get('enabled_since'),'rules':s.get('rules',{}),'items':items}

    @app.put('/api/gallery-connection/settings')
    def save_settings(payload:SettingsIn,_:Admin=Depends(current_admin),db=Depends(get_db)):
        s=config(db)
        if payload.key:
            key=payload.key.strip()
            if not key.startswith('wbm_gallery_') or len(key)<40:raise HTTPException(422,'Copy the key from gallery Settings > Booking connection.')
            s['credential']=encryptor().encrypt(key.encode()).decode()
        if payload.enabled:
            try:
                r=call_gallery(s,'GET','/api/integrations/wbm/status')
                if r.status_code!=200 or r.json().get('capabilities',{}).get('gallery_provisioning')!=1:raise ValueError()
            except Exception:raise HTTPException(422,'Cannot enable: update the gallery app, enable its connection and check the key.')
            if not s.get('enabled_since'):s['enabled_since']=utcnow().isoformat()
        s.update(enabled=payload.enabled,rules={k:v.model_dump() for k,v in payload.rules.items()})
        row=db.get(SystemSetting,KEY)
        if row:row.value=s
        else:db.add(SystemSetting(key=KEY,value=s))
        db.commit();return {'ok':True}

    @app.get('/api/gallery-connection/jobs')
    def jobs(_:Admin=Depends(current_admin),db=Depends(get_db)):
        rows=db.execute(select(GalleryProvision,Booking.title).join(Booking,Booking.id==GalleryProvision.booking_id).order_by(GalleryProvision.next_at.desc()).limit(100)).all()
        return [{**job_json(j),'couple':title} for j,title in rows]

    @app.get('/api/bookings/{bid}/gallery')
    def booking_gallery(bid:str,_:Admin=Depends(current_admin),db=Depends(get_db)):
        b=db.get(Booking,bid)
        if not b:raise HTTPException(404,'Booking not found.')
        job=db.get(GalleryProvision,bid)
        return job_json(job) if job else {'status':'not_created','result':{}}

    @app.post('/api/gallery-connection/jobs/{bid}/retry')
    def retry(bid:str,_:Admin=Depends(current_admin),db=Depends(get_db)):
        job=db.get(GalleryProvision,bid)
        if not job or job.status not in ('retry','needs_attention') or job.result:raise HTTPException(409,'This gallery does not need a retry.')
        if not eligible(db,db.get(Booking,bid)):raise HTTPException(409,'The booking is not eligible.')
        job.status='pending';job.next_at=utcnow();job.attempts=0;job.error=None;db.commit();return {'ok':True}

    @app.post('/api/gallery-connection/jobs/{bid}/reviewed')
    def reviewed(bid:str,_:Admin=Depends(current_admin),db=Depends(get_db)):
        job=db.get(GalleryProvision,bid)
        if not job or job.status!='needs_review' or not job.result:raise HTTPException(409,'No existing gallery needs review.')
        job.revision=revision(db,db.get(Booking,bid),config(db));job.status='created';job.error=None
        db.commit();return {'ok':True}

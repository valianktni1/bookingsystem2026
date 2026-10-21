"""Opt-in pull of explicit planner timing snapshots; no public receiving endpoint."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import DateTime, ForeignKey, JSON, String, select, func
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, SessionLocal, get_db
from .models import Admin, Booking, Brand, Client, FormSubmission, RecordKind, RecordStatus, Task
from .security import current_admin
from . import planner_integration as bridge
from .final_timings import validated_final_timings
from .timings_forms import effective_template, public_template, revision, validate_extra_answers, answer_snapshot

FALLBACK_DAYS=21


class PlannerTimingLink(Base):
    __tablename__='planner_timing_links'
    booking_id: Mapped[str]=mapped_column(String(36),ForeignKey('bookings.id',ondelete='CASCADE'),primary_key=True)
    next_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True)
    checked_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    state: Mapped[dict]=mapped_column(JSON,default=dict)


class PlannerTimingReceipt(Base):
    __tablename__='planner_timing_receipts'
    submission_id: Mapped[str]=mapped_column(String(36),primary_key=True)
    booking_id: Mapped[str]=mapped_column(String(36),ForeignKey('bookings.id',ondelete='CASCADE'),index=True)
    received_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict]=mapped_column(JSON)


def enabled(config):
    return bool(config.get('timings_enabled') and config.get('credential'))


def checked_payload(db,b):
    # An email is a discovery hint, never the sole identifier. Reject ambiguous
    # active native bookings before asking the planner to bind a unique account.
    others=db.scalars(select(Booking).join(Client).where(
        func.lower(func.trim(Client.email))==b.client.email.strip().lower(),Booking.event_date==b.event_date,
        Booking.brand==b.brand,Booking.kind==b.kind,Booking.legacy_source.is_(None),
        Booking.status.in_((RecordStatus.CONFIRMED,RecordStatus.IN_PROGRESS)))).all()
    if len(others)!=1 or others[0].id!=b.id:
        raise ValueError('Multiple bookings share this email and wedding date. Review the link before enabling it.')
    payload=bridge.invitation_payload(b)
    return {'booking_id':b.id,'email':payload['email'],'wedding_date':payload['wedding_date'],
            'template':public_template(effective_template(db,b.id))}


def store_submission(db,b,snapshot):
    """Called only for a matched booking after an explicit couple submission."""
    from .main import ensure_final_timings_document, audit, send_owner_notification_safely, sync_booking_calendar_safely
    if not isinstance(snapshot,dict) or len(json.dumps(snapshot))>100000: raise ValueError('Invalid planner submission.')
    sid=str(UUID(snapshot.get('submission_id','')))
    previous=db.get(PlannerTimingReceipt,sid)
    if previous:
        if previous.booking_id!=b.id or previous.snapshot!=snapshot: raise ValueError('Submission identifier conflict. Review the planner link.')
        return False
    if (snapshot.get('booking_id')!=b.id or snapshot.get('email')!=b.client.email.strip().lower()
            or snapshot.get('wedding_date')!=b.event_date.isoformat()):
        raise ValueError('Booking details changed. The planner submission was not applied.')
    # Serialize receiving with normal form edits, and preserve portal/imported
    # answers. A second source never silently replaces an existing submission.
    db.scalar(select(Booking).where(Booking.id==b.id).with_for_update())
    db.refresh(b)
    # Another receiver may have committed while this transaction waited for the row lock.
    previous=db.get(PlannerTimingReceipt,sid)
    if previous:
        if previous.booking_id!=b.id or previous.snapshot!=snapshot: raise ValueError('Submission identifier conflict. Review the planner link.')
        return False
    if b.archived_at or not bridge.eligible(db,b) or snapshot.get('wedding_date')!=b.event_date.isoformat() or snapshot.get('email')!=b.client.email.strip().lower():
        raise ValueError('The booking changed during transfer. Review it before receiving these timings.')
    existing=db.scalar(select(FormSubmission).where(FormSubmission.booking_id==b.id,FormSubmission.form_type=='final_timings'))
    if existing and existing.submission_source!='ivory_planner':
        raise ValueError('A final timings form is already saved from another source. Mark needs to review this planner submission separately.')
    config=effective_template(db,b.id);raw=snapshot.get('answers')
    if not isinstance(raw,dict) or raw.get('_template_revision')!=revision(config):
        raise ValueError('The photography questions changed. Reopen the planner preview before submitting again.')
    extra=validate_extra_answers(config,raw)
    values=validated_final_timings(db,b,raw);values.update(extra)
    values.update(_form_template=config,_answer_snapshot=answer_snapshot(config,values),
                  _planner_submission_id=sid,_planner_wedding_id=snapshot['wedding_id'])
    # Keep the exact planner timeline and photo list visible in the usual
    # answer view/PDF as well as in the immutable receipt.
    timeline=snapshot.get('timeline') or []
    if not isinstance(timeline,list) or not isinstance(snapshot.get('groups',[]),list): raise ValueError('Invalid planner timeline.')
    for i,event in enumerate(timeline,1):
        key=f'planner_activity_{i}'
        text=f"{int(event['start'])//60:02d}:{int(event['start'])%60:02d} - {event['title']}" + (f" - {event['location']}" if event.get('location') else '') + (f" - {event['instructions']}" if event.get('instructions') else '')
        values[key]=text
        values['_answer_snapshot'].append({'key':key,'label':f'Planner photography activity {i}','answer':text,'step':2})
    for i,title in enumerate(snapshot.get('groups',[]),1):
        key=f'planner_group_{i}';values[key]=str(title)
        values['_answer_snapshot'].append({'key':key,'label':f'Planner photo group {i}','answer':str(title),'step':3})
    if existing:
        existing.data=values;existing.updated_at=bridge.utcnow()
    else:
        existing=FormSubmission(booking_id=b.id,form_type='final_timings',data=values,submission_source='ivory_planner');db.add(existing)
    db.flush()
    b.form_data={**(b.form_data or {}),'ceremony_time':values['ceremony_time']}
    workflow=dict(b.workflow_state or {});workflow.pop('final_timings_review',None);b.workflow_state=workflow
    task=db.scalar(select(Task).where(Task.booking_id==b.id,Task.workflow_key=='wbm_review_final_timings').limit(1))
    if task: task.completed=False
    else: db.add(Task(booking_id=b.id,title='Review final wedding timings from planner',workflow_key='wbm_review_final_timings'))
    ensure_final_timings_document(db,b,existing)
    db.add(PlannerTimingReceipt(submission_id=sid,booking_id=b.id,received_at=bridge.utcnow(),snapshot=snapshot))
    audit(db,'submit_form','booking',b.id,{'form_type':'final_timings','source':'ivory_planner','submission_id':sid})
    db.commit()  # receipt makes a lost HTTP acknowledgement safe to replay
    send_owner_notification_safely(db,b,'final_timings_submitted_admin',section='journey',
        extra_values={'form_name':'Final Wedding Timings from planner','submission_action':'submitted'})
    sync_booking_calendar_safely(db,b)
    return True


def check_booking(db,b,config):
    # Serialize first-link creation and polling across the worker and reminder loop.
    db.scalar(select(Booking).where(Booking.id==b.id).with_for_update())
    db.refresh(b)
    now=bridge.utcnow();link=db.get(PlannerTimingLink,b.id)
    if not link:
        link=PlannerTimingLink(booking_id=b.id,next_at=now,state={});db.add(link);db.flush()
    state={'status':'unavailable','active':False}
    try:
        payload=checked_payload(db,b)
        response=bridge.call_planner(config,'POST','/api/integrations/wbm/timings/link',payload)
        if response.status_code==404: state={'status':'not_matched','active':False}
        elif response.status_code!=200: state={'status':'needs_attention','active':False,'error':'Planner link unavailable or ambiguous; the normal form remains the fallback.'}
        else:
            result=response.json()
            if any(result.get(k)!=payload[k] for k in ('booking_id','email','wedding_date')) or not result.get('wedding_id'): raise ValueError('Unexpected planner match.')
            state={'status':'received' if result.get('latest_status')=='received' else 'linked','active':result.get('active') is True,'wedding_id':result['wedding_id']}
            if result.get('latest_status')=='needs_attention': state.update(status='needs_attention',active=False,error='The last planner submission needs correction; the normal form remains the fallback.')
            snapshot=result.get('submission')
            if snapshot:
                if snapshot.get('wedding_id')!=result['wedding_id']: raise ValueError('Planner submission link mismatch.')
                try:
                    store_submission(db,b,snapshot)
                    state['status']='received'
                    ack={'submission_id':snapshot['submission_id'],'status':'received','message':'Received in Mark’s booking system.'}
                except (ValueError,ValidationError) as exc:
                    db.rollback()
                    # Only validation text, never raw response bodies/secrets.
                    error=exc.errors()[0]['msg'] if isinstance(exc,ValidationError) else str(exc)
                    ack={'submission_id':snapshot.get('submission_id'),'status':'needs_attention','message':str(error)[:500]}
                    state.update(status='needs_attention',active=False,error=ack['message'])
                reply=bridge.call_planner(config,'POST',f'/api/integrations/wbm/timings/{b.id}/ack',ack)
                if reply.status_code!=200: state.update(error='Submission saved; planner receipt confirmation will retry.')
    except Exception:
        db.rollback()
        # Fail open to the existing form; no stale active flag can hold it.
        state={'status':'unavailable','active':False,'error':'Planner check failed. Normal timing reminders remain available.'}
    link=db.get(PlannerTimingLink,b.id)
    if not link: link=PlannerTimingLink(booking_id=b.id,next_at=now,state={});db.add(link)
    link.checked_at=now;link.state=state
    link.next_at=now+timedelta(minutes=2 if state['status'] in ('linked','received') else 60)
    db.commit()
    return state


def run_timings_jobs():
    with SessionLocal() as db:
        config=bridge.connection(db)
        if not enabled(config): return
        now=bridge.utcnow()
        rows=db.scalars(select(Booking).outerjoin(PlannerTimingLink).where(
            Booking.brand==Brand.WBM,Booking.kind==RecordKind.WEDDING,
            Booking.archived_at.is_(None),Booking.legacy_source.is_(None),Booking.is_test.is_(False),
            Booking.automation_suppressed.is_(False),Booking.event_date>=now.date(),
            Booking.status.in_((RecordStatus.CONFIRMED,RecordStatus.IN_PROGRESS)),
            (PlannerTimingLink.booking_id.is_(None))|(PlannerTimingLink.next_at<=now))
            .order_by(PlannerTimingLink.next_at.asc().nullsfirst(),Booking.event_date,Booking.id).limit(25)).all()
        for b in rows:
            if bridge.eligible(db,b): check_booking(db,b,config)
            else:
                db.scalar(select(Booking).where(Booking.id==b.id).with_for_update())
                link=db.get(PlannerTimingLink,b.id)
                if not link: link=PlannerTimingLink(booking_id=b.id,next_at=now,state={});db.add(link)
                link.next_at=now+timedelta(hours=6);link.state={'status':'not_eligible','active':False};db.commit()


def hold_timing_invitation(db,b,today):
    config=bridge.connection(db)
    if not enabled(config) or b.archived_at or not b.event_date or b.event_date<today or not bridge.eligible(db,b): return False
    # A validated saved receipt wins even if the planner is subsequently down.
    if any(row.snapshot.get('wedding_date')==b.event_date.isoformat() and row.snapshot.get('email')==b.client.email.strip().lower()
           for row in db.scalars(select(PlannerTimingReceipt).where(PlannerTimingReceipt.booking_id==b.id))):
        return True
    # Refresh immediately before deciding to hold an automatic email.
    result=check_booking(db,b,config)
    if any(row.snapshot.get('wedding_date')==b.event_date.isoformat() and row.snapshot.get('email')==b.client.email.strip().lower() for row in db.scalars(select(PlannerTimingReceipt).where(PlannerTimingReceipt.booking_id==b.id))): return True
    fallback=b.event_date-timedelta(days=FALLBACK_DAYS)
    return bool(result.get('status')=='linked' and result.get('active') and today<fallback)


def register_routes(app):
    @app.get('/api/planner-invitations/timings')
    def timings_status(_: Admin=Depends(current_admin),db=Depends(get_db)):
        return [{'booking_id':row.booking_id,'couple':title,'checked_at':row.checked_at,
                 'fallback_date':bday-timedelta(days=FALLBACK_DAYS) if bday else None,**row.state}
                for row,title,bday in db.execute(select(PlannerTimingLink,Booking.title,Booking.event_date).join(Booking)).all()]

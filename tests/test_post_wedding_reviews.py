import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TEST_ROOT=Path(__file__).parent
DB_FILE=TEST_ROOT/'test-post-wedding-reviews.db'
os.environ['DATABASE_URL']=f'sqlite:///{DB_FILE}'
os.environ['STORAGE_ROOT']=str(TEST_ROOT/'post-wedding-review-storage')
os.environ['ADMIN_EMAIL']='mark@example.com'
os.environ['ADMIN_PASSWORD']='SecureTestPassword!123'
os.environ['SESSION_SECRET']='post-wedding-review-tests-secret-at-least-32-characters'
os.environ['COOKIE_SECURE']='false'

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.database import SessionLocal,engine
from app.models import Booking,Brand,BusinessProfile,Client,EmailLog,EmailTemplate,RecordKind,RecordStatus,ReminderLog,SystemSetting
from app.main import app
import app.main as main
import app.email_service as emails
import app.post_wedding_reviews as reviews
from app.workflow_studio import workflow_rule
from app.bootstrap import bootstrap
from app.business_time import business_today


@pytest.fixture
def setup(monkeypatch):
    engine.dispose();DB_FILE.unlink(missing_ok=True)
    monkeypatch.setattr(main,'apply_quote_reply_safety',lambda *a,**kw: None)
    monkeypatch.setattr(emails,'smtp_ready',lambda *a: True)
    monkeypatch.setattr(emails,'smtp_credentials',lambda *a: ('sender@example.com','unused'))
    sent=[]
    monkeypatch.setattr(emails,'send_email_message',lambda message,brand: sent.append(message))
    with TestClient(app) as client:
        yield sent,client
    engine.dispose();DB_FILE.unlink(missing_ok=True)


def freeze(monkeypatch,today):
    monkeypatch.setattr(main,'business_today',lambda: today)
    monkeypatch.setattr(reviews,'business_today',lambda: today)


def wedding(db,event_date,**changes):
    b=Booking(brand=Brand.WBM,kind=RecordKind.WEDDING,status=RecordStatus.CONFIRMED,
              title='Emma & James',event_date=event_date,
              client=Client(first_name='Emma',last_name='Test',partner_name='James',email='couple@example.com'),
              workflow_state={'after_wedding':{'album':{'status':'designing'}}})
    for key,value in changes.items():setattr(b,key,value)
    db.add(b);db.commit();return b


def text(message):
    return message.get_body(preferencelist=('plain',)).get_content()


def run(db):
    return main.run_due_reminders(db,today=reviews.business_today())


def test_awards_cutoff_uses_uk_midnight():
    assert business_today(datetime(2027,4,30,22,59,tzinfo=timezone.utc))==date(2027,4,30)
    assert business_today(datetime(2027,4,30,23,0,tzinfo=timezone.utc))==date(2027,5,1)


def test_existing_install_gets_new_template_without_overwriting_edits(setup):
    with SessionLocal() as db:
        template=db.scalar(select(EmailTemplate).where(EmailTemplate.template_key==reviews.TEMPLATE_KEY))
        db.delete(template)
        manual=db.scalar(select(EmailTemplate).where(EmailTemplate.template_key=='review_request'))
        manual.body='My own wording';manual.is_active=False
        db.commit();bootstrap(db);db.commit()
        created=db.scalar(select(EmailTemplate).where(EmailTemplate.template_key==reviews.TEMPLATE_KEY))
        assert created.body==reviews.BODY
        created.body='My edited check-in';created.is_active=False
        db.commit();bootstrap(db);db.commit()
        assert created.body=='My edited check-in' and not created.is_active
        assert manual.body=='My own wording' and not manual.is_active


def test_exact_fourteenth_day_once_and_completed_bookings_supported(setup,monkeypatch):
    sent,_=setup
    day=date(2027,4,16)
    with SessionLocal() as db:
        b=wedding(db,day,status=RecordStatus.COMPLETED)
        freeze(monkeypatch,day+timedelta(days=13))
        assert run(db)['sent']==0
        freeze(monkeypatch,day+timedelta(days=14))
        assert run(db)['sent']==1
        assert run(db)['sent']==0
        assert len(sent)==1
        body=text(sent[0])
        assert body.startswith('Hey Guys,')
        assert 'second year running' in body and 'both vote separately' in body
        assert body.index(reviews.COUNTY_BRIDES_URL)<body.index(reviews.FACEBOOK_REVIEW_URL)<body.index(reviews.GOOGLE_REVIEW_URL)
        assert b.workflow_state['after_wedding']['review_request']['sent_at']
        assert b.workflow_state['after_wedding']['album']['status']=='designing'
        assert db.scalar(select(EmailLog).where(EmailLog.booking_id==b.id)).template_key==reviews.TEMPLATE_KEY
        b.event_date=day+timedelta(days=1);db.commit()
        freeze(monkeypatch,day+timedelta(days=15))
        assert run(db)['sent']==0


@pytest.mark.parametrize('send_date',[date(2027,5,1),date(2027,5,15),date(2028,4,1)])
def test_post_deadline_removes_whole_voting_section(setup,monkeypatch,send_date):
    sent,_=setup;freeze(monkeypatch,send_date)
    with SessionLocal() as db:
        wedding(db,send_date-timedelta(days=14))
        assert run(db)['sent']==1
    for kind in ('plain','html'):
        body=sent[0].get_body(preferencelist=(kind,)).get_content()
        assert 'countybrides' not in body and 'vote separately' not in body
        assert 'second year running' not in body and '30 April 2027' not in body
        assert reviews.GOOGLE_REVIEW_URL in body and reviews.FACEBOOK_REVIEW_URL in body
        assert 'It would be lovely' in body
        assert '{county_brides_request}' not in body


@pytest.mark.parametrize('key',['review_request',reviews.TEMPLATE_KEY])
def test_previous_manual_or_automatic_review_prevents_duplicate(setup,monkeypatch,key):
    sent,_=setup;today=date(2027,4,20);freeze(monkeypatch,today)
    with SessionLocal() as db:
        b=wedding(db,today-timedelta(days=14))
        db.add(EmailLog(booking_id=b.id,template_key=key,recipient=b.client.email,subject='Earlier review',status='sent'))
        db.commit()
        assert run(db)['sent']==0
        assert not sent


@pytest.mark.parametrize('changes',[
    {'status':RecordStatus.ENQUIRY},{'status':RecordStatus.QUOTED},{'status':RecordStatus.CANCELLED},
    {'automation_suppressed':True},{'legacy_source':'studio_ninja'},
    {'archived_at':datetime.now(timezone.utc)},
    {'brand':Brand.IVORY,'kind':RecordKind.DIGITAL},
])
def test_ineligible_records_are_not_contacted(setup,monkeypatch,changes):
    sent,_=setup;today=date(2027,4,20);freeze(monkeypatch,today)
    with SessionLocal() as db:
        wedding(db,today-timedelta(days=14),**changes)
        assert run(db)['sent']==0
        assert not sent


def test_old_weddings_are_not_bulk_contacted_on_deployment(setup,monkeypatch):
    sent,_=setup;today=date(2027,4,20);freeze(monkeypatch,today)
    with SessionLocal() as db:
        wedding(db,today-timedelta(days=100))
        assert run(db)['sent']==0
        assert not sent


def test_disabled_rule_respected_and_template_bootstrapped(setup,monkeypatch):
    sent,_=setup;today=date(2027,4,20);freeze(monkeypatch,today)
    with SessionLocal() as db:
        assert workflow_rule(db,reviews.TEMPLATE_KEY)=={'mode':'automatic','days':14}
        template=db.scalar(select(EmailTemplate).where(EmailTemplate.template_key==reviews.TEMPLATE_KEY))
        assert template.body==reviews.BODY and template.subject==reviews.SUBJECT
        wedding(db,today-timedelta(days=14))
        db.add(SystemSetting(key='workflow_studio_wbm',value={'rules':{reviews.TEMPLATE_KEY:{'mode':'off','days':14}}}))
        db.commit();db.info.clear()
        assert run(db)['sent']==0
        assert not sent


def test_failure_before_cutoff_retries_without_vote_afterwards(setup,monkeypatch):
    sent,_=setup;freeze(monkeypatch,date(2027,4,30))
    with SessionLocal() as db:
        b=wedding(db,date(2027,4,16))
        def fail(*args):raise RuntimeError('Simulated mail failure')
        monkeypatch.setattr(emails,'send_email_message',fail)
        assert run(db)['failed']==1
        assert not b.workflow_state['after_wedding'].get('review_request')
        reminder=db.scalar(select(ReminderLog).where(ReminderLog.booking_id==b.id))
        reminder.next_attempt_at=None;db.commit()
        freeze(monkeypatch,date(2027,5,1))
        monkeypatch.setattr(emails,'send_email_message',lambda message,brand: sent.append(message))
        assert run(db)['sent']==1
        assert reviews.COUNTY_BRIDES_URL not in text(sent[0])


def test_rendered_email_retry_enforces_deadline_in_both_mime_parts(setup,monkeypatch):
    sent,_=setup;freeze(monkeypatch,date(2027,5,1))
    with SessionLocal() as db:
        b=wedding(db,date(2027,4,16))
        body=reviews.BODY.replace('{county_brides_request}',reviews.COUNTY_BRIDES_REQUEST+'\n\n').replace('{review_request_intro}','It would also be lovely')
        profile=db.scalar(select(BusinessProfile).where(BusinessProfile.brand==Brand.WBM))
        emails.send_rendered_email(b,profile,b.client.email,reviews.SUBJECT,body,template_key=reviews.TEMPLATE_KEY)
    for kind in ('plain','html'):
        assert reviews.COUNTY_BRIDES_URL not in sent[0].get_body(preferencelist=(kind,)).get_content()

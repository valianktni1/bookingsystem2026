import os
from pathlib import Path
from datetime import datetime,timedelta,timezone,date
from decimal import Decimal
from unittest.mock import Mock
import pytest
import httpx

ROOT=Path(__file__).parent
os.environ.update(DATABASE_URL=f'sqlite:///{ROOT / "test-v871.db"}',STORAGE_ROOT=str(ROOT/'v871-storage'),COOKIE_SECURE='false',ADMIN_EMAIL='mark@example.com',ADMIN_PASSWORD='SecureTestPassword!123',SESSION_SECRET='planner-invitation-test-secret-longer-than-32',ACCOUNTS_INTEGRATION_ENABLED='false')
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.database import SessionLocal,engine
from app.models import Booking,Client,Invoice,Quote,EmailLog,SystemSetting,Brand,RecordKind,RecordStatus
from app import planner_integration as bridge

NOW=datetime(2026,10,16,12,0,tzinfo=timezone.utc)

@pytest.fixture
def client(monkeypatch):
    engine.dispose();(ROOT/'test-v871.db').unlink(missing_ok=True)
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW)
    with TestClient(app) as c:
        assert c.post('/api/auth/login',json={'email':'mark@example.com','password':'SecureTestPassword!123'}).status_code==200
        yield c


def configure(enabled=True):
    with SessionLocal() as db:
        row=db.get(SystemSetting,bridge.KEY)
        value={'enabled':enabled,'enabled_since':(NOW-timedelta(hours=1)).isoformat(),'credential':bridge.encryptor().encrypt(b'wbm_planner_'+b'x'*48).decode()}
        if row:row.value=value
        else:db.add(SystemSetting(key=bridge.KEY,value=value))
        db.commit()


def booking(*,paid=100,receipt_status='sent',sent_at=NOW,legacy=False,test=False,partner='Dan',day=date(2027,6,19)):
    with SessionLocal() as db:
        c=Client(first_name='Sophie',partner_name=partner,email='sophie@example.com');db.add(c);db.flush()
        b=Booking(client_id=c.id,brand=Brand.WBM,kind=RecordKind.WEDDING,status=RecordStatus.CONFIRMED,title='Sophie & Dan',event_date=day,deposit_amount=100,legacy_source='studio_ninja' if legacy else None,is_test=test)
        db.add(b);db.flush()
        i=Invoice(booking_id=b.id,brand=Brand.WBM,sequence=871,number='WBM'+b.id,total=899,paid=paid,status='part_paid');db.add(i)
        db.add(Quote(booking_id=b.id,status='accepted'))
        db.add(EmailLog(booking_id=b.id,template_key='payment_received',planner_deposit_eligible=paid>=100,status=receipt_status,recipient=c.email,subject='Deposit received',sent_at=sent_at))
        db.commit();return b.id


def response(booking_id,status='queued'):
    return httpx.Response(201,json={'booking_id':booking_id,'wedding_id':'planner-test','status':status})


def test_waits_30_minutes_from_successful_confirmation_and_survives_new_sessions(client,monkeypatch):
    configure();bid=booking();send=Mock(return_value=response(bid));monkeypatch.setattr(bridge,'call_planner',send)
    bridge.run_planner_jobs();send.assert_not_called()
    with SessionLocal() as db:
        assert bridge.aware(db.get(bridge.PlannerInvitation,bid).due_at)==NOW+timedelta(minutes=30)
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW+timedelta(minutes=29,seconds=59));bridge.run_planner_jobs();send.assert_not_called()
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW+timedelta(minutes=30));bridge.run_planner_jobs();assert send.call_count==1
    payload=send.call_args.args[-1]
    assert payload=={'booking_id':bid,'first_name':'Sophie','partner_first_name':'Dan','email':'sophie@example.com','wedding_date':'2027-06-19'}
    send.return_value=httpx.Response(200,json={'booking_id':bid,'wedding_id':'planner-test','status':'sent'})
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW+timedelta(minutes=32));bridge.run_planner_jobs()
    assert send.call_args.args[1]=='GET'
    with SessionLocal() as db:assert db.get(bridge.PlannerInvitation,bid).status=='sent'
    bridge.run_planner_jobs();assert send.call_count==2


@pytest.mark.parametrize('changes',[{'paid':50},{'receipt_status':'failed'},{'legacy':True},{'test':True},{'sent_at':NOW-timedelta(days=1)}])
def test_no_partial_failed_import_test_or_historical_invites(client,monkeypatch,changes):
    configure();bid=booking(**changes);send=Mock();monkeypatch.setattr(bridge,'call_planner',send);bridge.run_planner_jobs()
    with SessionLocal() as db:assert db.get(bridge.PlannerInvitation,bid) is None
    send.assert_not_called()


def test_missing_details_and_cancellation_are_visible_without_email(client,monkeypatch):
    configure();bid=booking(partner='');send=Mock();monkeypatch.setattr(bridge,'call_planner',send);bridge.run_planner_jobs()
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW+timedelta(minutes=31));bridge.run_planner_jobs();send.assert_not_called()
    jobs=client.get('/api/planner-invitations/jobs').json();assert jobs[0]['status']=='needs_attention'
    with SessionLocal() as db:
        b=db.get(Booking,bid);b.client.partner_name='Dan';db.commit()
    assert client.post(f'/api/planner-invitations/jobs/{bid}/retry').status_code==200
    with SessionLocal() as db:b=db.get(Booking,bid);b.status=RecordStatus.CANCELLED;db.commit()
    bridge.run_planner_jobs();send.assert_not_called()
    assert client.get('/api/planner-invitations/jobs').json()[0]['status']=='cancelled'


def test_lost_response_replays_identical_payload_without_second_scheduled_job(client,monkeypatch):
    configure();bid=booking();seen=[]
    def send(config,method,path,payload=None):
        seen.append(dict(payload))
        if len(seen)==1:raise httpx.ReadTimeout('lost response')
        return response(bid)
    monkeypatch.setattr(bridge,'call_planner',send);bridge.run_planner_jobs()
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW+timedelta(minutes=31));bridge.run_planner_jobs()
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW+timedelta(minutes=34));bridge.run_planner_jobs()
    assert len(seen)==2 and seen[0]==seen[1]
    with SessionLocal() as db:assert len(db.scalars(select(bridge.PlannerInvitation)).all())==1


def test_existing_account_conflict_stops_for_review(client,monkeypatch):
    configure();bid=booking();monkeypatch.setattr(bridge,'call_planner',lambda *args,**kwargs:httpx.Response(409,json={'error':'Account exists'}))
    bridge.run_planner_jobs();monkeypatch.setattr(bridge,'utcnow',lambda:NOW+timedelta(minutes=31));bridge.run_planner_jobs()
    assert client.get('/api/planner-invitations/jobs').json()[0]['status']=='needs_attention'


def test_opt_in_connection_test_encryption_pause_and_auth(client,monkeypatch):
    bid=booking();send=Mock(return_value=httpx.Response(200,json={'ok':True,'ready':True}));monkeypatch.setattr(bridge,'call_planner',send)
    bridge.run_planner_jobs();send.assert_not_called()
    key='wbm_planner_'+'x'*48
    result=client.put('/api/planner-invitations/settings',json={'enabled':True,'key':key});assert result.status_code==200,result.text
    assert key not in client.get('/api/planner-invitations/settings').text
    with SessionLocal() as db:
        config=bridge.connection(db);assert config['credential']!=key and bridge.credential(config)==key
    assert client.put('/api/planner-invitations/settings',json={'enabled':False}).status_code==200
    bridge.run_planner_jobs();assert send.call_count==1
    client.post('/api/auth/logout');assert client.get('/api/planner-invitations/settings').status_code==401


def test_failed_full_deposit_email_does_not_use_an_earlier_partial_receipt(client,monkeypatch):
    configure();bid=booking(paid=50)
    with SessionLocal() as db:
        inv=db.scalar(select(Invoice).where(Invoice.booking_id==bid));inv.paid=100
        db.add(EmailLog(booking_id=bid,template_key='payment_received',planner_deposit_eligible=True,status='failed',recipient='sophie@example.com',subject='Top up receipt',body='Top up confirmation',sent_at=NOW+timedelta(minutes=10)))
        db.commit()
    send=Mock();monkeypatch.setattr(bridge,'call_planner',send);bridge.run_planner_jobs();send.assert_not_called()
    with SessionLocal() as db:
        assert db.get(bridge.PlannerInvitation,bid) is None
        db.add(EmailLog(booking_id=bid,template_key='payment_received',planner_deposit_eligible=True,status='sent',recipient='sophie@example.com',subject='Retried top up',sent_at=NOW+timedelta(minutes=20)))
        db.commit()
    monkeypatch.setattr(bridge,'utcnow',lambda:NOW+timedelta(minutes=20));bridge.run_planner_jobs();send.assert_not_called()
    with SessionLocal() as db:assert bridge.aware(db.get(bridge.PlannerInvitation,bid).due_at)==NOW+timedelta(minutes=50)


def test_recording_payments_marks_only_full_deposit_receipts_and_preserves_failed_retry(client,monkeypatch):
    from app import main
    configure();bid=booking(paid=0,receipt_status='failed')
    with SessionLocal() as db:invoice_id=db.scalar(select(Invoice.id).where(Invoice.booking_id==bid))
    monkeypatch.setattr(main,'smtp_ready',lambda *args:True)
    monkeypatch.setattr(main,'send_tracked_booking_template_email',lambda *args,**kw:('Payment','Receipt','a'*64))
    paid=client.post(f'/api/invoices/{invoice_id}/payments',json={'amount':50,'paid_date':'2026-10-16','payment_type':'bank_transfer'})
    assert paid.status_code==201,paid.text
    with SessionLocal() as db:
        logs=db.scalars(select(EmailLog).where(EmailLog.booking_id==bid,EmailLog.status=='sent')).all()
        assert len(logs)==1 and not logs[0].planner_deposit_eligible
    def fail(*args,**kwargs):raise RuntimeError('Mock SMTP unavailable')
    monkeypatch.setattr(main,'send_tracked_booking_template_email',fail)
    paid=client.post(f'/api/invoices/{invoice_id}/payments',json={'amount':50,'paid_date':'2026-10-16','payment_type':'bank_transfer'})
    assert paid.status_code==201,paid.text
    with SessionLocal() as db:
        failed=db.scalar(select(EmailLog).where(EmailLog.booking_id==bid,EmailLog.planner_deposit_eligible.is_(True)))
        assert failed.status=='failed'
        failed.body='Retained payment confirmation';db.commit();failed_id=failed.id
    bridge.run_planner_jobs()
    with SessionLocal() as db:assert db.get(bridge.PlannerInvitation,bid) is None
    monkeypatch.setattr(main,'send_rendered_email',lambda *a,**kw:None)
    retry=client.post(f'/api/communications/failures/email/{failed_id}/retry')
    assert retry.status_code==200,retry.text
    with SessionLocal() as db:
        sent=db.scalar(select(EmailLog).where(EmailLog.booking_id==bid,EmailLog.status=='sent',EmailLog.planner_deposit_eligible.is_(True)))
        assert sent is not None


def test_upgrade_adds_receipt_marker_without_marking_or_replacing_old_receipts(client):
    from app.migrations import apply_safe_migrations
    bid=booking()
    with engine.begin() as conn:
        conn.exec_driver_sql('ALTER TABLE email_logs DROP COLUMN planner_deposit_eligible')
    apply_safe_migrations()
    with SessionLocal() as db:
        receipt=db.scalar(select(EmailLog).where(EmailLog.booking_id==bid))
        assert receipt.subject=='Deposit received'
        assert receipt.planner_deposit_eligible is False

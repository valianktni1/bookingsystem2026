import os
from pathlib import Path
from datetime import date, datetime, timezone
from copy import deepcopy
os.environ.update(DATABASE_URL='sqlite:////tmp/wbm-v861.db',STORAGE_ROOT='/tmp/wbm-v861-storage',COOKIE_SECURE='false',ADMIN_EMAIL='mark@example.com',ADMIN_PASSWORD='SecureTestPassword!123',SESSION_SECRET='local-test-only-session-secret-123456',REMINDERS_ENABLED='false')
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, engine
from app.models import Booking, Quote, EmailLog, ContractAcceptance, Task

ORIGINAL={'message':'Can we have outdoor ceremony photographs?', 'primary_first_name':'Alex', 'answer_snapshot':[{'key':'message','label':'Your original message','answer':'Can we have outdoor ceremony photographs?'}]}

def setup_record(client):
    assert client.post('/api/auth/login',json={'email':'mark@example.com','password':'SecureTestPassword!123'}).status_code==200
    r=client.post('/api/bookings',json={'brand':'wbm','kind':'wedding','status':'confirmed','title':'Alex & Sam — review test','client':{'first_name':'Alex','last_name':'Example','partner_name':'Sam','email':'alex@example.com'},'event_date':'2027-05-15','venue_or_project':'Test Hall','deposit_amount':100}).json()
    with SessionLocal() as db:
        b=db.get(Booking,r['id']);b.form_data={'website_enquiry':deepcopy(ORIGINAL)}
        b.workflow_state={'source':'website_enquiry','received_at':'2026-09-26T10:00:00+00:00'}
        db.add(Quote(booking_id=b.id,status='accepted',total=630,deposit_amount=100,accepted_at=datetime.now(timezone.utc),line_items=[{'name':'Saved Bronze Package','description':'Half Day Photography\nCeremony photographs\nOnline gallery','total':475},{'name':'Two extra hours','description':'Two hours of photography','total':155}]))
        db.add(EmailLog(booking_id=b.id,template_key='new_enquiry_admin',recipient='mark@example.com',subject='Original enquiry notification',body='Original message retained in the email.',status='sent'))
        db.add(ContractAcceptance(booking_id=b.id,contract_title='Wedding agreement',contract_version='test',contract_body='Saved signed agreement wording.',accepted_name='Alex Example',accepted_email='alex@example.com',accepted_at=datetime.now(timezone.utc),supplier_signed_name='Mark Powell',supplier_signed_at=datetime.now(timezone.utc)))
        db.commit()
    return r['id']

def test_original_enquiry_preserved_and_read_only_fallback():
    engine.dispose();Path('/tmp/wbm-v861.db').unlink(missing_ok=True)
    with TestClient(app) as client:
        assert client.get('/api/bookings/missing/original-enquiry').status_code==401
        bid=setup_record(client)
        got=client.get(f'/api/bookings/{bid}/original-enquiry').json()
        assert got['answers']==ORIGINAL
        portal=client.post(f'/api/bookings/{bid}/portal',json={'expires_days':365}).json()
        token=portal['url'].split('/client/')[1]
        form={'primary_full_name':'Alex Example','primary_phone':'07700 900111','primary_email':'alex@example.com','partner_full_name':'Sam Example','partner_phone':'07700 900222','partner_email':'sam@example.com','street_address':'1 Test Road','town':'Manchester','county':'Greater Manchester','postcode':'M1 1AA','wedding_date':'2027-05-15','ceremony_time':'13:00','venue_name':'Test Hall','ceremony_details':'Test Hall ceremony','reception_details':'Test Hall reception','package_selected':'Saved Bronze Package','payment_plan':'standard','wedding_party_size':'8','unique_events':'None','guest_uploads':'Yes please','additional_information':'Updated booking notes','highlight_music':''}
        response=client.post(f'/api/client/{token}/forms',json={'form_type':'booking_form','data':form})
        assert response.status_code==200,response.text
        assert client.get(f'/api/bookings/{bid}/original-enquiry').json()['answers']==ORIGINAL
        with SessionLocal() as db:
            b=db.get(Booking,bid);b.form_data={};db.commit()
        fallback=client.get(f'/api/bookings/{bid}/original-enquiry').json()
        assert fallback['source']=='saved_notification' and fallback['body']=='Original message retained in the email.'
        with SessionLocal() as db:
            assert db.get(Booking,bid).form_data=={}
        assert client.get('/api/bookings/missing/original-enquiry').status_code==404
        # Restore only synthetic fixture for browser checks.
        with SessionLocal() as db:
            b=db.get(Booking,bid);b.form_data={'website_enquiry':deepcopy(ORIGINAL)};db.commit()
        Path('/tmp/wbm-v861-record.txt').write_text(bid)

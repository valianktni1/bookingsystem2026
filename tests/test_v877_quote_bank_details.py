"""Disposable bookings only; no SMTP or external integrations."""
import asyncio
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_v857_quote_templates import reset_database,login,create_waiting_quote
from app import main
from app.database import SessionLocal
from app.models import Booking,BusinessProfile,Brand,Invoice

OLD={'account_name':'Example Old Bank','sort_code':'01-02-03','account_number':'00123456'}
NEW={'account_name':'Example New Bank','sort_code':'04-05-06','account_number':'00987654'}

@pytest.fixture
def client(monkeypatch):
    reset_database()
    async def idle():await asyncio.sleep(86400)
    for name in ('reminder_loop','calendar_retry_loop','accounts_sync_loop','growth_sync_loop','sms_automation_loop','planner_invitation_loop'):
        monkeypatch.setattr(main,name,idle)
    monkeypatch.setattr(main,'send_owner_notification_safely',Mock(return_value={'sent':False}))
    monkeypatch.setattr(main,'sync_booking_calendar_safely',Mock(return_value={}))
    with TestClient(main.app) as c:
        login(c)
        with SessionLocal() as db:
            db.scalar(select(BusinessProfile).where(BusinessProfile.brand==Brand.WBM)).bank_details=OLD;db.commit()
        banks=c.get('/api/quote-bank-accounts').json()
        banks[0].update(OLD);banks[1].update(NEW)
        assert c.put('/api/quote-bank-accounts',json={'accounts':banks}).status_code==200
        yield c

@pytest.mark.parametrize('account,expected',[('primary',OLD),('alternate',NEW)])
def test_live_quote_and_preview_use_only_chosen_snapshot(client,account,expected):
    b,token=create_waiting_quote(client);bid=b['id']
    assert client.put(f'/api/bookings/{bid}/quote/preparation',json={'bank_account_id':account,'required_addons':[],'discounts':[]}).status_code==200
    before=client.get(f'/api/client/{token}').json()
    assert before['quote_bank_details']==expected
    assert client.get(f'/api/bookings/{bid}/quote-preview-data').json()['quote_bank_details']==expected
    banks=client.get('/api/quote-bank-accounts').json()
    for bank in banks:bank['account_number']='11223344'
    assert client.put('/api/quote-bank-accounts',json={'accounts':banks}).status_code==200
    with SessionLocal() as db:
        db.scalar(select(BusinessProfile).where(BusinessProfile.brand==Brand.WBM)).bank_details={**OLD,'account_number':'88776655'};db.commit()
    assert client.get(f'/api/client/{token}').json()['quote_bank_details']==expected
    after=client.get(f'/api/client/{token}').json()
    assert after['record']['payment_reference']==before['record']['payment_reference']
    assert set(after['quote_bank_details'])=={'account_name','sort_code','account_number'}


def test_accepted_quote_uses_its_invoice_snapshot_and_pdf_agrees(client):
    import fitz
    b,token=create_waiting_quote(client);bid=b['id']
    assert client.put(f'/api/bookings/{bid}/quote/preparation',json={'bank_account_id':'alternate','required_addons':[],'discounts':[]}).status_code==200
    package=client.get('/api/catalog?brand=wbm').json()['packages'][0]
    accepted=client.post(f'/api/client/{token}/quote',json={'package_id':package['id'],'addon_ids':[],'confirmed':True})
    assert accepted.status_code==201,accepted.text
    with SessionLocal() as db:
        row=db.get(Booking,bid);workflow=dict(row.workflow_state)
        workflow['quote_preparation']={**workflow['quote_preparation'],'bank_details':OLD}
        row.workflow_state=workflow;db.commit()
    view=client.get(f'/api/client/{token}').json();assert view['quote_bank_details']==NEW
    invoice_id=view['quote']['invoice_id']
    pdf=client.get(f'/api/client/{token}/invoices/{invoice_id}/invoice.pdf');assert pdf.status_code==200
    with fitz.open(stream=pdf.content,filetype='pdf') as doc:text=''.join(page.get_text() for page in doc)
    assert NEW['account_number'] in text and OLD['account_number'] not in text


def test_unsnapshotted_and_protected_import_follow_existing_bank_fallback(client):
    b,token=create_waiting_quote(client);bid=b['id']
    assert client.get(f'/api/client/{token}').json()['quote_bank_details']==OLD
    with SessionLocal() as db:
        row=db.get(Booking,bid);row.legacy_source='studio_ninja';row.automation_suppressed=True
        row.workflow_state={**(row.workflow_state or {}),'quote_preparation':{'bank_details':NEW}};db.commit()
        before=row.workflow_state
    assert client.get(f'/api/client/{token}').json()['quote_bank_details']==OLD
    with SessionLocal() as db:assert db.get(Booking,bid).workflow_state==before


def test_secure_quote_bank_data_requires_valid_portal_or_admin(client):
    assert client.get('/api/client/not-a-token').status_code in (403,404)
    with TestClient(main.app) as anonymous:
        assert anonymous.get('/api/bookings/not-a-booking/quote-preview-data').status_code==401

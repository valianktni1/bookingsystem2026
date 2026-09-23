import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
ROOT = TEST_ROOT.parent
DB_FILE = TEST_ROOT / "test-v857.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v857-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"


from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.main import app
from app.models import EmailLog


def reset_database():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v857.db-journal").unlink(missing_ok=True)


def login(client):
    response = client.post("/api/auth/login", json={
        "email": "mark@example.com",
        "password": "SecureTestPassword!123",
    })
    assert response.status_code == 200


def create_waiting_quote(client):
    response = client.post("/api/bookings", json={
        "brand": "wbm",
        "kind": "wedding",
        "status": "quoted",
        "title": "Abdul & Analise",
        "client": {
            "first_name": "Abdul",
            "last_name": "Client",
            "partner_name": "Analise Client",
            "email": "abdul-v8451@example.com",
        },
        "event_date": (date.today() + timedelta(days=200)).isoformat(),
        "venue_or_project": "Wedding venue",
    })
    assert response.status_code == 201, response.text
    booking = response.json()
    portal = client.post(f"/api/bookings/{booking['id']}/portal", json={
        "expires_days": 90,
    })
    assert portal.status_code == 201, portal.text
    token = portal.json()["url"].split("/client/")[1]
    with SessionLocal() as db:
        db.add(EmailLog(
            booking_id=booking["id"],
            template_key="quote",
            recipient="abdul-v8451@example.com",
            subject="Your wedding quote",
            status="sent",
        ))
        db.commit()
    return booking, token



def test_templates_restrict_client_choices_and_snapshot_bank_details():
    from app.models import Booking, BusinessProfile, Brand, Invoice
    from app.email_service import template_values
    from app.pdf import invoice_pdf
    import fitz
    reset_database()
    with TestClient(app) as client:
        assert client.get('/api/quote-templates').status_code == 401
        login(client)
        booking, token = create_waiting_quote(client)
        bid = booking['id']
        catalog = client.get('/api/catalog?brand=wbm').json()
        gold = next(x for x in catalog['packages'] if x['code']=='gold')
        other = next(x for x in catalog['packages'] if x['id']!=gold['id'])
        addon = next(x for x in catalog['addons'] if not x['is_discount'])
        banks = client.get('/api/quote-bank-accounts').json()
        banks[1].update(account_name='New Business Bank', sort_code='123456', account_number='12345678')
        assert client.put('/api/quote-bank-accounts',json={'accounts':banks}).status_code==200
        with SessionLocal() as db:
            old_invoice=Invoice(booking_id=bid, brand=Brand.WBM, sequence=9000, number='OLD-9000', total=25, paid=0, status='unpaid')
            db.add(old_invoice); db.commit()
            old_invoice_id=old_invoice.id
        offer = dict(name='Gold only', subject='Gold options for {client_first_name}', body='Hello {client_first_name}',
                     package_ids=[gold['id']], optional_addon_ids=[], required_addons=[], discounts=[], bank_account_id='alternate', email_subject='Stored quote wording', email_body='Stored body')
        created=client.post('/api/quote-templates',json=offer)
        assert created.status_code==201, created.text
        tid=created.json()['id']
        assert client.put(f'/api/bookings/{bid}/quote/preparation',json=offer).status_code==200
        result=client.get(f'/api/client/{token}').json()
        assert [p['id'] for p in result['catalog']['packages']]==[gold['id']]
        assert result['catalog']['addons']==[]
        assert client.post(f'/api/client/{token}/quote',json={'package_id':other['id'],'addon_ids':[],'confirmed':True}).status_code==422
        assert client.post(f'/api/client/{token}/quote',json={'package_id':gold['id'],'addon_ids':[addon['id']],'confirmed':True}).status_code==422
        # Editing template and account configuration must not rewrite this quote.
        assert client.put('/api/quote-templates/'+tid,json={**offer,'package_ids':[other['id']]}).status_code==200
        assert client.get(f'/api/bookings/{bid}/email-centre').json()['quote_email']['subject']=='Stored quote wording'
        banks[1]['account_number']='87654321'
        assert client.put('/api/quote-bank-accounts',json={'accounts':banks}).status_code==200
        with SessionLocal() as db:
            b=db.get(Booking,bid)
            profile=db.scalar(select(BusinessProfile).where(BusinessProfile.brand==Brand.WBM))
            assert template_values(b,profile)['bank_account_number']=='12345678'
        accepted=client.post(f'/api/client/{token}/quote',json={'package_id':gold['id'],'addon_ids':[],'confirmed':True})
        assert accepted.status_code==201, accepted.text
        assert client.put(f'/api/bookings/{bid}/quote/preparation',json=offer).status_code==409
        with SessionLocal() as db:
            inv=db.scalar(select(Invoice).where(Invoice.booking_id==bid, Invoice.id!=old_invoice_id))
            profile=db.scalar(select(BusinessProfile).where(BusinessProfile.brand==Brand.WBM))
            doc=fitz.open(stream=invoice_pdf(inv,profile),filetype='pdf')
            text=''.join(page.get_text() for page in doc)
            assert '12345678' in text and '87654321' not in text
            old_pdf=fitz.open(stream=invoice_pdf(db.get(Invoice,old_invoice_id),profile),filetype='pdf')
            assert '12345678' not in ''.join(page.get_text() for page in old_pdf)
        assert client.delete('/api/quote-templates/'+tid).status_code==204
        assert client.get('/api/quote-templates').json()==[]


def test_legacy_protection_and_old_api_compatibility():
    from app.models import Booking, BusinessProfile, Brand
    from app.quote_templates import booking_bank_details
    reset_database()
    with TestClient(app) as client:
        login(client)
        b,token=create_waiting_quote(client)
        bid=b['id']
        c=client.get('/api/catalog?brand=wbm').json()
        payload={'package_ids':[c['packages'][0]['id']], 'optional_addon_ids':[], 'required_addons':[], 'discounts':[]}
        assert client.put(f'/api/bookings/{bid}/quote/preparation',json=payload).status_code==200
        # An old cached browser only sending charges must retain the new restriction.
        assert client.put(f'/api/bookings/{bid}/quote/preparation',json={'required_addons':[],'discounts':[]}).status_code==200
        assert len(client.get(f'/api/client/{token}').json()['catalog']['packages'])==1
        assert client.put(f'/api/bookings/{bid}/quote/preparation',json={**payload,'package_ids':[]}).status_code==422
        assert client.put(f'/api/bookings/{bid}/quote/preparation',json={**payload,'package_ids':['missing']}).status_code==422
        with SessionLocal() as db:
            row=db.get(Booking,bid);row.legacy_source='studio_ninja';row.automation_suppressed=True
            row.workflow_state={**row.workflow_state,'quote_preparation':{**row.workflow_state['quote_preparation'],'bank_details':{'account_number':'dont-use'}}}
            db.commit()
            profile=db.scalar(select(BusinessProfile).where(BusinessProfile.brand==Brand.WBM))
            assert booking_bank_details(row,profile)==(profile.bank_details or {})
        assert client.put(f'/api/bookings/{bid}/quote/preparation',json=payload).status_code==409
        assert len(client.get(f'/api/client/{token}').json()['catalog']['packages'])==len(c['packages'])

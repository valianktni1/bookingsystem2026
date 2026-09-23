import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
ROOT = TEST_ROOT.parent
DB_FILE = TEST_ROOT / "test-v858.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v858-storage")
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
    (TEST_ROOT / "test-v858.db-journal").unlink(missing_ok=True)


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




def test_preview_matches_real_quote_and_does_not_write_or_create_links():
    from app.models import Booking, ClientPortalToken, Invoice, Quote, AuditLog
    reset_database()
    with TestClient(app) as client:
        assert client.get('/quote-preview/not-a-booking').status_code==401
        assert client.get('/api/bookings/not-a-booking/quote-preview-data').status_code==401
        login(client)
        booking, token=create_waiting_quote(client)
        bid=booking['id']
        catalog=client.get('/api/catalog?brand=wbm').json()
        package=catalog['packages'][0]
        addon=next(x for x in catalog['addons'] if not x['is_discount'])
        banks=client.get('/api/quote-bank-accounts').json()
        banks[1].update(label='New bank',account_name='Test account',sort_code='123456',account_number='12345678')
        assert client.put('/api/quote-bank-accounts',json={'accounts':banks}).status_code==200
        payload={'package_ids':[package['id']], 'optional_addon_ids':[], 'required_addons':[{'addon_id':addon['id'],'price':50}], 'discounts':[], 'bank_account_id':'alternate'}
        assert client.put(f'/api/bookings/{bid}/quote/preparation',json=payload).status_code==200
        def counts():
            with SessionLocal() as db:
                return [db.scalar(select(func.count()).select_from(model)) for model in (ClientPortalToken, Invoice, Quote, EmailLog, AuditLog)]
        before=counts()
        real=client.get(f'/api/client/{token}').json()
        preview=client.get(f'/api/bookings/{bid}/quote-preview-data')
        assert preview.status_code==200,preview.text
        assert preview.json()['catalog']==real['catalog']
        assert preview.json()['quote_preparation']==real['quote_preparation']
        assert preview.json()['preview_bank']['account_number']=='12345678'
        assert 'preview_bank' not in real
        page=client.get('/quote-preview/'+bid)
        assert page.status_code==200
        assert 'client.js?v=quote-review-v8-58' in page.text
        assert counts()==before
        # A booking ID is not a client portal token and cannot accept the quote.
        assert client.post(f'/api/client/{bid}/quote',json={'package_id':package['id'],'confirmed':True}).status_code==404
        with SessionLocal() as db:
            row=db.get(Booking,bid);row.legacy_source='studio_ninja';row.automation_suppressed=True;db.commit()
        assert client.get(f'/api/bookings/{bid}/quote-preview-data').status_code==409

import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
ROOT = TEST_ROOT.parent
DB_FILE = TEST_ROOT / "test-v8451.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v8451-storage")
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
    (TEST_ROOT / "test-v8451.db-journal").unlink(missing_ok=True)


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


def test_sent_unaccepted_quote_can_add_a_free_album_without_email_or_invoice():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking, token = create_waiting_quote(client)
        catalog = client.get("/api/catalog?brand=wbm").json()
        album = next(row for row in catalog["addons"] if row["code"] == "album_offer")
        gold = next(row for row in catalog["packages"] if row["code"] == "gold")

        with SessionLocal() as db:
            emails_before = db.scalar(select(func.count()).select_from(EmailLog))

        saved = client.put(f"/api/bookings/{booking['id']}/quote/preparation", json={
            "required_addons": [{"addon_id": album["id"], "price": 0}],
            "discounts": [],
        })
        assert saved.status_code == 200, saved.text
        assert saved.json()["required_addons"][0]["name"] == "Wedding album offer"
        assert saved.json()["required_addons"][0]["price"] == 0
        assert client.get(f"/api/bookings/{booking['id']}").json()["invoices"] == []
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(EmailLog)) == emails_before

        public_quote = client.get(f"/api/client/{token}").json()
        assert public_quote["quote"] is None
        assert public_quote["quote_preparation"]["required_addons"][0]["price"] == 0

        accepted = client.post(f"/api/client/{token}/quote", json={
            "package_id": gold["id"],
            "addon_ids": [],
            "confirmed": True,
        })
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["invoice"]["total"] == gold["price"]
        album_line = next(
            row for row in accepted.json()["invoice"]["line_items"]
            if row["name"] == "Wedding album offer"
        )
        assert album_line["total"] == 0
        assert client.put(f"/api/bookings/{booking['id']}/quote/preparation", json={
            "required_addons": [], "discounts": [],
        }).status_code == 409


def test_edit_button_is_visible_only_while_sent_quote_is_unaccepted():
    script = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert 'alreadySent=latestEmailLog(d,"quote")?.status==="sent"' in script
    assert 'alreadySent?"Edit sent quote":"Prepare quote"' in script
    assert '<button id="edit-quote" class="primary">Edit quote</button>' in script
    assert 'alreadySent?"Save quote changes":"Save quote & review email"' in script
    assert 'if(!alreadySent)await reviewAndSendQuoteEmail(r,body)' in script
    assert "The same live quote link will show the saved changes" in script


def teardown_module():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v8451.db-journal").unlink(missing_ok=True)

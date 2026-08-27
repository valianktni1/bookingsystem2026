import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"
os.environ["INVOICE_START"] = "2000"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, ClientPortalToken, EmailLog


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def create_booking(client):
    return client.post("/api/bookings", json={
        "brand": "wbm", "kind": "wedding", "status": "confirmed",
        "title": "Alex & Sam",
        "client": {
            "first_name": "Alex", "last_name": "Taylor", "partner_name": "Sam",
            "email": "alex@example.com", "phone": "07700 900111",
        },
        "event_date": (date.today() + timedelta(days=240)).isoformat(),
        "venue_or_project": "Test Hall", "package_name": "Gold",
        "quoted_total": 899, "deposit_amount": 100,
    }).json()


def test_client_email_centre_recommends_contract_and_sends_template_or_manual(monkeypatch):
    reset_database()
    sent = []

    def fake_send(db, booking, profile, template, portal_url=None, **kwargs):
        sent.append({
            "template_key": template.template_key,
            "subject": template.subject,
            "body": template.body,
            "portal_url": portal_url,
        })
        return template.subject, template.body

    monkeypatch.setattr("app.main.send_booking_template_email", fake_send)

    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        portal = client.post(f"/api/bookings/{booking['id']}/portal", json={
            "expires_days": 365,
        }).json()
        token = portal["url"].split("/client/")[1]
        assert client.post(f"/api/client/{token}/forms", json={
            "form_type": "booking_form",
            "data": {
                "primary_full_name": "Alex Taylor", "primary_phone": "07700 900111",
                "primary_email": "alex@example.com", "partner_full_name": "Sam Taylor",
                "street_address": "1 Test Street", "town": "Manchester",
                "county": "Greater Manchester", "postcode": "M1 1AA",
                "wedding_date": booking["event_date"], "ceremony_time": "13:00",
                "ceremony_details": "Test Hall", "reception_details": "Test Hall",
                "package_selected": "Gold", "payment_plan": "standard",
                "wedding_party_size": "8", "unique_events": "None",
            },
        }).status_code == 200

        centre = client.get(f"/api/bookings/{booking['id']}/email-centre")
        assert centre.status_code == 200
        centre_data = centre.json()
        assert centre_data["recipient"] == "alex@example.com"
        assert centre_data["recommended_template_key"] == "contract_reminder"
        assert centre_data["account_link_included"] is True
        assert centre_data["manual_only"] is False
        contract_template = next(item for item in centre_data["templates"]
                                 if item["template_key"] == "contract_reminder")

        template_send = client.post(f"/api/bookings/{booking['id']}/email-centre/send", json={
            "mode": "template", "template_key": "contract_reminder",
            "subject": contract_template["subject"],
            "body": contract_template["body"] + "\n\nPlease shout if you need any help.",
        })
        assert template_send.status_code == 200
        assert template_send.json()["account_link_included"] is True
        assert sent[-1]["template_key"] == "contract_reminder"
        tracked_url = urlparse(sent[-1]["portal_url"])
        assert parse_qs(tracked_url.query)["tab"] == ["agreement"]
        assert parse_qs(tracked_url.query)["email_access"]
        assert "Please shout if you need any help." in sent[-1]["body"]

        manual_send = client.post(f"/api/bookings/{booking['id']}/email-centre/send", json={
            "mode": "manual", "subject": "A quick wedding update",
            "body": "Hi {client_first_name},\n\nHere is a quick update.\n\nMark",
        })
        assert manual_send.status_code == 200
        assert manual_send.json()["template_key"] == "manual_client_email"
        assert "/client/" in sent[-1]["portal_url"]
        assert "?tab=" not in sent[-1]["portal_url"]

        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 2
            # One original admin-created link plus one fresh link for each email.
            assert db.scalar(select(func.count()).select_from(ClientPortalToken)) == 3


def test_imported_client_email_centre_requires_deliberate_one_email_confirmation(monkeypatch):
    reset_database()
    sent = []

    def fake_send(db, booking, profile, template, portal_url=None, **kwargs):
        sent.append(template.template_key)
        return template.subject, template.body

    monkeypatch.setattr("app.main.send_booking_template_email", fake_send)

    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        with SessionLocal() as db:
            row = db.get(Booking, booking["id"])
            row.legacy_source = "studio_ninja"
            row.automation_suppressed = True
            db.commit()

        centre = client.get(f"/api/bookings/{booking['id']}/email-centre").json()
        assert centre["manual_only"] is True
        blocked = client.post(f"/api/bookings/{booking['id']}/email-centre/send", json={
            "mode": "manual", "subject": "Manual update", "body": "Hi Alex, update.",
        })
        assert blocked.status_code == 422
        assert sent == []

        allowed = client.post(f"/api/bookings/{booking['id']}/email-centre/send", json={
            "mode": "manual", "subject": "Manual update", "body": "Hi Alex, update.",
            "manual_reason": "Mark deliberately chose to contact this imported client",
            "manual_confirmation": "SEND ONE MANUAL EMAIL",
        })
        assert allowed.status_code == 200
        assert allowed.json()["manual_only"] is True
        assert allowed.json()["automation_suppressed"] is True
        assert sent == ["manual_client_email"]

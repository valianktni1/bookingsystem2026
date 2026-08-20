import importlib
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v816.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v816-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v816-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, Brand, EmailLog, MailboxReply


def booking_payload(email="sophie@example.com"):
    return {
        "brand": "wbm", "kind": "wedding", "status": "enquiry",
        "title": "Sophie & James",
        "client": {
            "first_name": "Sophie", "last_name": "Taylor",
            "partner_name": "James", "email": email,
        },
        "event_date": "2027-10-04", "venue_or_project": "Peckforton Castle",
        "quoted_total": 1299, "deposit_amount": 100,
    }


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v816.db").unlink(missing_ok=True)


def login(client):
    response = client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    })
    assert response.status_code == 200


def test_quote_email_access_is_tracked_but_admin_preview_is_not(monkeypatch):
    reset_database()
    main_module = importlib.import_module("app.main")
    delivered = []

    def fake_send(db, booking, profile, template, portal_url=None, **kwargs):
        delivered.append(portal_url)
        return "Your wedding quote", f"Open your quote here: {portal_url}"

    monkeypatch.setattr(main_module, "smtp_ready", lambda brand=None: True)
    monkeypatch.setattr(main_module, "send_booking_template_email", fake_send)

    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json=booking_payload()).json()
        response = client.post(
            f"/api/bookings/{booking['id']}/quote/send",
            json={"expires_days": 365},
        )
        assert response.status_code == 200, response.text
        direct_url = response.json()["url"]
        assert "email_access=" not in direct_url
        assert len(delivered) == 1
        tracked_url = delivered[0]
        assert "email_access=" in tracked_url

        direct = urlparse(direct_url)
        portal_token = direct.path.rsplit("/", 1)[-1]
        assert client.get(f"/api/client/{portal_token}").status_code == 200
        with SessionLocal() as db:
            log = db.scalar(select(EmailLog).where(
                EmailLog.booking_id == booking["id"], EmailLog.template_key == "quote"
            ))
            assert log.link_access_count == 0
            assert log.first_link_accessed_at is None

        access_token = parse_qs(urlparse(tracked_url).query)["email_access"][0]
        assert client.get(
            f"/api/client/{portal_token}?email_access={access_token}"
        ).status_code == 200
        with SessionLocal() as db:
            log = db.scalar(select(EmailLog).where(
                EmailLog.booking_id == booking["id"], EmailLog.template_key == "quote"
            ))
            assert log.link_access_count == 1
            assert log.first_link_accessed_at is not None
            assert log.last_link_accessed_at is not None

        status = client.get(f"/api/bookings/{booking['id']}/portal").json()
        quote_log = next(item for item in status["emails"] if item["template_key"] == "quote")
        assert quote_log["link_tracking_enabled"] is True
        assert quote_log["link_access_count"] == 1


def test_conversation_contains_only_booking_sent_mail_and_exact_client_inbox(monkeypatch):
    reset_database()
    mail_routes = importlib.import_module("app.mail_routes")
    requested = []

    def fake_correspondent(brand, email_address, limit):
        requested.append((brand, email_address, limit))
        return [{
            "uid": "42", "subject": "Wedding question", "body": "Hi Mark, can I ask a question?",
            "date": "2026-08-20T08:30:00+00:00", "reply_to_email": email_address,
            "from_name": "Sophie Taylor", "unread": True, "attachments": [],
        }]

    monkeypatch.setattr(mail_routes, "imap_ready", lambda brand=None: True)
    monkeypatch.setattr(mail_routes, "list_correspondent_messages", fake_correspondent)
    monkeypatch.setattr(
        mail_routes, "list_sent_messages_to_correspondent",
        lambda brand, email_address, limit: [],
    )

    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json=booking_payload()).json()
        with SessionLocal() as db:
            db.add(EmailLog(
                booking_id=booking["id"], template_key="quote",
                recipient="sophie@example.com", subject="Your wedding quote",
                body="Here is your secure wedding quote.", status="sent",
            ))
            db.add(EmailLog(
                booking_id=booking["id"], template_key="new_enquiry_admin",
                recipient="mark@perfectweddingsbymark.uk", subject="Private admin copy",
                body="This must not appear in the couple conversation.", status="sent",
            ))
            db.add(MailboxReply(
                brand=Brand.WBM, booking_id=booking["id"],
                recipient="sophie@example.com", subject="Re: Wedding question",
                body="Of course, Sophie.", message_id="<reply-v816@example.com>",
                status="sent",
            ))
            db.commit()

        response = client.get(f"/api/bookings/{booking['id']}/conversation")
        assert response.status_code == 200, response.text
        result = response.json()
        assert requested == [(Brand.WBM, "sophie@example.com", 60)]
        assert result["privacy_scope"] == "Exact booking and couple email addresses only"
        assert result["sent_count"] == 2
        assert result["received_count"] == 1
        assert len(result["messages"]) == 3
        assert "Private admin copy" not in {item["subject"] for item in result["messages"]}
        assert {item["direction"] for item in result["messages"]} == {"sent", "received"}


def test_conversation_includes_both_exact_booking_form_addresses(monkeypatch):
    reset_database()
    mail_routes = importlib.import_module("app.mail_routes")
    inbox_requests = []
    sent_requests = []

    def fake_inbox(brand, email_address, limit):
        inbox_requests.append(email_address)
        uid = "51" if email_address == "sophie@example.com" else "52"
        return [{
            "uid": uid, "subject": f"From {email_address}", "body": "Hello Mark",
            "date": "2026-08-20T09:00:00+00:00", "reply_to_email": email_address,
            "from_name": email_address.split("@", 1)[0].title(), "unread": False,
            "attachments": [],
        }]

    def fake_sent(brand, email_address, limit):
        sent_requests.append(email_address)
        return []

    monkeypatch.setattr(mail_routes, "imap_ready", lambda brand=None: True)
    monkeypatch.setattr(mail_routes, "list_correspondent_messages", fake_inbox)
    monkeypatch.setattr(mail_routes, "list_sent_messages_to_correspondent", fake_sent)

    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json=booking_payload()).json()
        with SessionLocal() as db:
            record = db.get(Booking, booking["id"])
            record.form_data = {
                "primary_email": "sophie@example.com",
                "partner_email": "james@example.com",
            }
            db.commit()

        result = client.get(f"/api/bookings/{booking['id']}/conversation").json()
        assert result["client_emails"] == ["sophie@example.com", "james@example.com"]
        assert inbox_requests == ["sophie@example.com", "james@example.com"]
        assert sent_requests == ["sophie@example.com", "james@example.com"]
        assert result["received_count"] == 2


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v816.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v816.db-journal").unlink(missing_ok=True)

import os
from pathlib import Path

TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "mail-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "mail-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, ClientPortalToken, EmailLog, MailboxReply


def booking_payload(title="Sophie & James", email="sophie@example.com"):
    return {
        "brand": "wbm", "kind": "wedding", "status": "confirmed", "title": title,
        "client": {"first_name": "Sophie", "last_name": "Taylor", "email": email},
        "event_date": "2026-10-04", "venue_or_project": "Peckforton Castle",
        "quoted_total": 1299, "deposit_amount": 100,
    }


def fake_message(uid="42", email="sophie@example.com"):
    return {
        "uid": uid, "brand": "wbm", "from_name": "Sophie Taylor",
        "from_email": email, "reply_to_name": "Sophie Taylor",
        "reply_to_email": email, "to": "mark@perfectweddingsbymark.uk",
        "subject": "Wedding question", "date": "2026-08-06T10:30:00+00:00",
        "message_id": f"<message-{uid}@example.com>", "in_reply_to": "",
        "references": "", "unread": False, "body": "Hi Mark, can I ask a question?",
        "attachments": [],
    }


def test_unified_inbox_matches_booking_and_sends_threaded_reply(monkeypatch):
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    monkeypatch.setattr("app.mail_routes.mailbox_status", lambda brand: {
        "brand": brand.value,
        "address": "mark@perfectweddingsbymark.uk" if brand.value == "wbm" else "admin@ivorydigital.uk",
        "configured": True, "connected": True, "total": 4, "unread": 1, "error": None,
    })
    monkeypatch.setattr("app.mail_routes.imap_ready", lambda brand=None: True)
    monkeypatch.setattr("app.mail_routes.smtp_ready", lambda brand=None: True)
    monkeypatch.setattr("app.mail_routes.list_inbox_messages", lambda brand, limit, unread: [
        {key: value for key, value in fake_message().items()
         if key not in ("body", "attachments", "reply_to_name")}
    ] if brand.value == "wbm" else [])
    monkeypatch.setattr(
        "app.mail_routes.read_inbox_message",
        lambda brand, uid, mark_seen=True: fake_message(uid),
    )
    sent = []
    monkeypatch.setattr(
        "app.mail_routes.send_email_message",
        lambda message, brand: sent.append((message, brand)),
    )
    monkeypatch.setattr("app.mail_routes.append_to_sent", lambda brand, message: True)

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        booking = client.post("/api/bookings", json=booking_payload()).json()
        inbox = client.get("/api/mail/messages").json()
        assert inbox["messages"][0]["booking"]["id"] == booking["id"]
        opened = client.get("/api/mail/wbm/messages/42").json()
        assert opened["booking"]["title"] == "Sophie & James"
        reply = client.post("/api/mail/wbm/messages/42/reply", json={
            "body": "Hi Sophie, of course. I will help with that.",
            "booking_id": booking["id"], "include_account_link": True,
        })
        assert reply.status_code == 201, reply.text
        assert reply.json()["account_link_included"] is True
        assert reply.json()["copied_to_sent"] is True
        assert len(sent) == 1
        message, brand = sent[0]
        assert brand.value == "wbm"
        assert message["To"] == "sophie@example.com"
        assert message["In-Reply-To"] == "<message-42@example.com>"
        assert message["Subject"] == "Re: Wedding question"
        assert "OPEN YOUR WEDDING ACCOUNT" in message.get_body(
            preferencelist=("plain",)
        ).get_content()
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(MailboxReply)) == 1
            assert db.scalar(select(func.count()).select_from(EmailLog).where(
                EmailLog.template_key == "mail_reply")) == 1
            assert db.scalar(select(func.count()).select_from(ClientPortalToken).where(
                ClientPortalToken.booking_id == booking["id"])) == 1


def test_imported_studio_ninja_manual_reply_never_creates_portal_link(monkeypatch):
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    monkeypatch.setattr(
        "app.mail_routes.read_inbox_message",
        lambda brand, uid, mark_seen=True: fake_message(uid, "legacy@example.com"),
    )
    monkeypatch.setattr("app.mail_routes.send_email_message", lambda message, brand: None)
    monkeypatch.setattr("app.mail_routes.append_to_sent", lambda brand, message: False)
    monkeypatch.setattr("app.mail_routes.smtp_ready", lambda brand=None: True)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        booking = client.post("/api/bookings", json=booking_payload(
            title="Imported Couple", email="legacy@example.com"
        )).json()
        with SessionLocal() as db:
            row = db.get(Booking, booking["id"])
            row.legacy_source = "studio_ninja"
            row.legacy_id = "legacy-mail-test"
            row.automation_suppressed = True
            db.commit()
        reply = client.post("/api/mail/wbm/messages/84/reply", json={
            "body": "Hi, this is a deliberate manual reply.",
            "booking_id": booking["id"], "include_account_link": True,
        })
        assert reply.status_code == 201, reply.text
        assert reply.json()["account_link_included"] is False
        assert reply.json()["account_link_skipped_for_import"] is True
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(ClientPortalToken).where(
                ClientPortalToken.booking_id == booking["id"])) == 0

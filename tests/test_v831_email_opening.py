import hashlib
import os
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v831.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v831-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v831-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.email_service import build_email_message
from app.main import app
from app.models import Booking, BusinessProfile, EmailLog


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v831.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v831.db-journal").unlink(missing_ok=True)


def login(client):
    response = client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    })
    assert response.status_code == 200


def booking_payload():
    return {
        "brand": "wbm", "kind": "wedding", "status": "enquiry",
        "title": "Sophie & James",
        "client": {
            "first_name": "Sophie", "last_name": "Taylor",
            "partner_name": "James", "email": "sophie@example.com",
        },
        "event_date": "2027-10-04", "venue_or_project": "Peckforton Castle",
        "quoted_total": 1299, "deposit_amount": 100,
    }


def test_email_open_and_general_secure_link_access_are_recorded(monkeypatch):
    reset_database()
    monkeypatch.setattr("app.mail_routes.imap_ready", lambda brand=None: False)
    tracking_token = "opaque-v831-email-token-with-enough-entropy"
    tracking_hash = hashlib.sha256(tracking_token.encode("utf-8")).hexdigest()

    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json=booking_payload()).json()
        portal = client.post(
            f"/api/bookings/{booking['id']}/portal", json={"expires_days": 365}
        ).json()
        portal_token = portal["url"].split("/client/", 1)[1]

        with SessionLocal() as db:
            db.add(EmailLog(
                booking_id=booking["id"], template_key="enquiry_received",
                recipient="sophie@example.com", subject="We received your enquiry",
                body="Hi Sophie", status="sent", tracking_token_hash=tracking_hash,
            ))
            db.add(EmailLog(
                booking_id=booking["id"], template_key="manual_client_email",
                recipient="sophie@example.com", subject="An earlier email",
                body="Historic", status="sent",
            ))
            db.commit()

        first = client.get(f"/api/public/email-open/{tracking_token}.gif")
        second = client.get(f"/api/public/email-open/{tracking_token}.gif")
        assert first.status_code == 200
        assert first.headers["content-type"].startswith("image/gif")
        assert first.headers["cache-control"].startswith("no-store")
        assert first.content == second.content

        opened = client.get(
            f"/api/client/{portal_token}?email_access={tracking_token}"
        )
        assert opened.status_code == 200

        status = client.get(f"/api/bookings/{booking['id']}/portal").json()
        tracked = next(row for row in status["emails"]
                       if row["template_key"] == "enquiry_received")
        historic = next(row for row in status["emails"]
                        if row["template_key"] == "manual_client_email")
        assert tracked["open_tracking_enabled"] is True
        assert tracked["first_opened_at"] is not None
        assert tracked["last_opened_at"] is not None
        assert tracked["open_count"] == 2
        assert tracked["first_link_accessed_at"] is not None
        assert tracked["link_access_count"] == 1
        assert historic["open_tracking_enabled"] is False
        assert historic["first_opened_at"] is None

        conversation = client.get(
            f"/api/bookings/{booking['id']}/conversation"
        ).json()
        message = next(row for row in conversation["messages"]
                       if row["subject"] == "We received your enquiry")
        assert message["open_count"] == 2
        assert message["link_access_count"] == 1


def test_tracker_is_html_only_and_ui_uses_honest_wording():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking_id = client.post("/api/bookings", json=booking_payload()).json()["id"]
        with SessionLocal() as db:
            booking = db.get(Booking, booking_id)
            profile = db.scalar(select(BusinessProfile).where(
                BusinessProfile.brand == booking.brand
            ))
            message = build_email_message(
                booking, profile, "Test subject", "Hi Sophie", "mark@example.com",
                open_tracking_url=(
                    "https://booking.weddingsbymark.uk/api/public/email-open/opaque.gif"
                ),
            )
            plain = message.get_body(preferencelist=("plain",)).get_content()
            html = message.get_body(preferencelist=("html",)).get_content()
            assert "/api/public/email-open/opaque.gif" not in plain
            assert "/api/public/email-open/opaque.gif" in html
            assert 'width="1" height="1"' in html

    root = Path(__file__).parents[1]
    javascript = (root / "app/static/app.js").read_text()
    index = (root / "app/static/index.html").read_text()
    assert "Opened (images loaded)" in javascript
    assert "Sent · open not detected" in javascript
    assert "Link accessed" in javascript
    assert "Privacy-protected inboxes" in javascript
    assert "/static/v831.css?v=email-opening-v8-31" in index


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v831.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v831.db-journal").unlink(missing_ok=True)

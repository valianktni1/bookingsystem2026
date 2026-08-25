import os
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v825.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v825-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v825-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main_module
from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, Brand, EmailLog, EmailTemplate, RecordStatus


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v825.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v825.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def create_enquiry(client):
    return client.post("/api/bookings", json={
        "brand": "wbm", "kind": "wedding", "status": "enquiry",
        "title": "Sophie & James",
        "client": {
            "first_name": "Sophie", "last_name": "Taylor",
            "partner_name": "James", "email": "sophie@example.com",
        },
        "event_date": "2027-10-04", "venue_or_project": "Peckforton Castle",
        "quoted_total": 1299, "deposit_amount": 100,
    }).json()


def test_quote_is_saved_then_one_email_copy_is_personalised_without_changing_master(monkeypatch):
    reset_database()
    delivered = []

    def fake_send(db, booking, profile, template, portal_url=None, **kwargs):
        delivered.append({
            "subject": template.subject,
            "body": template.body,
            "portal_url": portal_url,
            "template_id": template.id,
        })
        return template.subject, template.body

    monkeypatch.setattr(main_module, "smtp_ready", lambda brand=None: True)
    monkeypatch.setattr(main_module, "send_booking_template_email", fake_send)

    with TestClient(app) as client:
        login(client)
        booking = create_enquiry(client)

        saved = client.put(f"/api/bookings/{booking['id']}/quote/preparation", json={
            "required_addons": [], "discounts": [],
        })
        assert saved.status_code == 200
        assert saved.json()["prepared"] is True
        assert delivered == []

        centre = client.get(f"/api/bookings/{booking['id']}/email-centre").json()
        master = next(row for row in centre["templates"] if row["template_key"] == "quote")
        original_subject = master["subject"]
        original_body = master["body"]
        personal_line = "You asked about an earlier arrival, and that is absolutely fine."

        sent = client.post(f"/api/bookings/{booking['id']}/quote/send", json={
            "expires_days": 90,
            "subject": original_subject,
            "body": original_body + f"\n\n{personal_line}",
        })
        assert sent.status_code == 200, sent.text
        assert sent.json()["email_sent"] is True
        assert sent.json()["master_template_unchanged"] is True
        assert len(delivered) == 1
        assert personal_line in delivered[0]["body"]
        assert "email_access=" in delivered[0]["portal_url"]
        assert delivered[0]["template_id"] is None

        with SessionLocal() as db:
            stored_master = db.scalar(select(EmailTemplate).where(
                EmailTemplate.brand == Brand.WBM,
                EmailTemplate.template_key == "quote",
            ))
            stored_booking = db.get(Booking, booking["id"])
            email_log = db.scalar(select(EmailLog).where(
                EmailLog.booking_id == booking["id"],
                EmailLog.template_key == "quote",
            ))
            assert stored_master.subject == original_subject
            assert stored_master.body == original_body
            assert stored_booking.status == RecordStatus.QUOTED
            assert personal_line in email_log.body
            assert email_log.tracking_token_hash


def test_studio_ninja_quote_email_protection_is_unchanged(monkeypatch):
    reset_database()
    delivered = []
    monkeypatch.setattr(main_module, "smtp_ready", lambda brand=None: True)
    monkeypatch.setattr(
        main_module, "send_booking_template_email",
        lambda *args, **kwargs: delivered.append(True),
    )

    with TestClient(app) as client:
        login(client)
        booking = create_enquiry(client)
        with SessionLocal() as db:
            imported = db.get(Booking, booking["id"])
            imported.legacy_source = "studio_ninja"
            imported.legacy_id = "sn-v825-protected"
            imported.automation_suppressed = True
            db.commit()

        blocked = client.post(f"/api/bookings/{booking['id']}/quote/send", json={
            "expires_days": 90,
            "subject": "This must not send",
            "body": "Protected imported booking",
        })
        assert blocked.status_code == 409
        assert delivered == []


def test_quote_review_controls_are_wired_as_a_two_stage_flow():
    root = Path(__file__).parents[1]
    javascript = (root / "app/static/app.js").read_text()
    index = (root / "app/static/index.html").read_text()

    assert 'showModal("Review quote email"' in javascript
    assert "Your saved Quote email template remains unchanged" in javascript
    assert "These changes apply to this email only" in javascript
    assert "Save quote & review email" in javascript
    assert "Quote saved — nothing has been emailed" in javascript
    assert "Review email &amp; send" in javascript
    assert 'subject:value("#quote-email-subject").trim()' in javascript
    assert 'body:value("#quote-email-body").trim()' in javascript
    assert "/static/app.js?v=client-receipt-open-v8-28-4-2" in index
    assert "/static/catalog.css?v=quote-email-review-v8-25" in index


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v825.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v825.db-journal").unlink(missing_ok=True)

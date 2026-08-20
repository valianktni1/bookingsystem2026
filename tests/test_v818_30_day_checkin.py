import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v818.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v818-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v818-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.email_service import render_template, template_values
from app.main import app, run_due_reminders
from app.models import Booking, Brand, BusinessProfile, EmailLog, EmailTemplate


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v818.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v818.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def test_editable_template_and_automatic_thirty_day_delivery(monkeypatch):
    reset_database()
    delivered = []

    def fake_send(db, booking, profile, template, portal_url=None, **kwargs):
        values = template_values(booking, profile, portal_url)
        subject = render_template(template.subject, values)
        body = render_template(template.body, values)
        delivered.append((template.template_key, subject, body))
        return subject, body

    monkeypatch.setattr("app.main.send_booking_template_email", fake_send)

    wedding_day = date.today() + timedelta(days=30)
    days_back = wedding_day.weekday() or 7
    expected_call = wedding_day - timedelta(days=days_back)
    expected_call_text = f"Monday {expected_call.strftime('%d %B %Y')}"

    with TestClient(app) as client:
        login(client)
        templates = client.get("/api/communications/templates?brand=wbm").json()["templates"]
        template = next(row for row in templates if row["template_key"] == "check_in_30")
        assert template["usage_kind"] == "automatic"
        assert "{final_call_date}" in template["body"]

        edited_body = template["body"] + "\n\nI cannot wait to see you both!"
        edited = client.patch(f"/api/communications/templates/{template['id']}", json={
            "display_name": template["display_name"],
            "subject": template["subject"],
            "body": edited_body,
            "is_active": True,
        })
        assert edited.status_code == 200
        refreshed = client.get("/api/communications/templates?brand=wbm").json()["templates"]
        assert next(row for row in refreshed if row["template_key"] == "check_in_30")["body"] == edited_body

        booking = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "confirmed",
            "title": "Sophie & James",
            "client": {
                "first_name": "Sophie", "last_name": "Taylor",
                "partner_name": "James", "email": "sophie@example.com",
            },
            "event_date": wedding_day.isoformat(),
            "venue_or_project": "Peckforton Castle",
            "quoted_total": 899, "deposit_amount": 100,
        }).json()

        with SessionLocal() as db:
            assert run_due_reminders(db) == {"sent": 1, "skipped": 0, "failed": 0}
            assert run_due_reminders(db) == {"sent": 0, "skipped": 1, "failed": 0}
            email = db.scalar(select(EmailLog).where(
                EmailLog.booking_id == booking["id"],
                EmailLog.template_key == "check_in_30",
            ))
            assert email is not None

        assert len(delivered) == 1
        assert delivered[0][0] == "check_in_30"
        assert expected_call_text in delivered[0][2]
        assert "{final_call_date}" not in delivered[0][2]
        assert "I cannot wait to see you both!" in delivered[0][2]


def test_monday_wedding_uses_previous_monday():
    wedding_day = date(2026, 9, 21)  # Monday
    booking = Booking(brand=Brand.WBM, event_date=wedding_day)
    booking.client = type("ClientStub", (), {
        "first_name": "Sophie", "last_name": "Taylor", "email": "sophie@example.com",
        "phone": "", "partner_name": "James",
    })()
    profile = BusinessProfile(brand=Brand.WBM, display_name="Weddings By Mark")
    assert template_values(booking, profile)["final_call_date"] == "Monday 14 September 2026"


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v818.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v818.db-journal").unlink(missing_ok=True)

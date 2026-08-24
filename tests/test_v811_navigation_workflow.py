import os
from pathlib import Path

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
from app.models import EmailLog


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def test_v811_direct_workspace_and_booking_urls_return_the_admin_app():
    reset_database()
    with TestClient(app) as client:
        dashboard = client.get("/dashboard")
        booking = client.get("/bookings/example-booking/journey")
        assert dashboard.status_code == 200
        assert booking.status_code == 200
        assert "/static/v811.js?v=inline-pdf-hotfix-v8-28-4-1" in dashboard.text
        assert "/static/v811.css?v=inline-pdf-hotfix-v8-28-4-1" in dashboard.text
        assert "COMPLETE BACKUP V8.14" in dashboard.text
        assert "/static/v812.js?v=google-calendar-v8-12" in dashboard.text
        assert "/static/v812.css?v=google-calendar-v8-12" in dashboard.text
        assert client.get("/not-a-real-workspace").status_code == 404


def test_v811_today_queue_is_read_only_and_opens_new_enquiry_at_quote_action():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "enquiry",
            "title": "Taylor & Morgan",
            "client": {
                "first_name": "Taylor", "last_name": "Jones",
                "partner_name": "Morgan", "email": "taylor@example.com",
            },
            "event_date": "2027-04-17", "venue_or_project": "Test Hall",
            "quoted_total": 899, "deposit_amount": 100,
        }).json()

        queues = client.get("/api/workflow-queues")
        assert queues.status_code == 200
        row = next(item for item in queues.json()["queues"]["new_enquiries"]
                   if item["booking_id"] == booking["id"])
        assert row["section"] == "Journey"
        assert row["action"] == "send_quote"
        assert queues.json()["counts"]["new_enquiries"] == 1

        # Merely building the Today screen must never send an email.
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 0

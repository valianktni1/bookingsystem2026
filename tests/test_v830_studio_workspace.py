import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v830.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v830-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v830-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.main import app
from app.models import AuditLog, EmailLog, Task


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v830.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v830.db-journal").unlink(missing_ok=True)


def login(client):
    response = client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    })
    assert response.status_code == 200


def wedding_payload(status="confirmed", event_date=None):
    return {
        "brand": "wbm", "kind": "wedding", "status": status,
        "title": "Completion Test Couple",
        "client": {
            "first_name": "Completion", "last_name": "Test",
            "partner_name": "Couple", "email": "complete@example.com",
        },
        "event_date": (event_date or (date.today() - timedelta(days=2))).isoformat(),
        "venue_or_project": "Test Wedding Venue", "package_name": "Silver Package 2",
        "quoted_total": 699, "deposit_amount": 100,
    }


def test_complete_and_reopen_wedding_are_deliberate_retained_actions():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json=wedding_payload()).json()
        booking_id = booking["id"]

        completed = client.post(f"/api/bookings/{booking_id}/complete")
        assert completed.status_code == 200, completed.text
        result = completed.json()
        assert result["status"] == "completed"
        assert result["workflow_state"]["completion"]["previous_status"] == "confirmed"
        assert result["workflow_state"]["completion"]["completed_by"] == "mark@example.com"
        assert any(row["id"] == booking_id and row["status"] == "completed"
                   for row in client.get("/api/bookings").json())
        assert all(row["booking_id"] != booking_id
                   for rows in client.get("/api/workflow-queues").json()["queues"].values()
                   for row in rows if row.get("update_type") != "email_failure")

        with SessionLocal() as db:
            assert db.scalar(select(EmailLog).where(EmailLog.booking_id == booking_id)) is None
            assert db.scalar(select(AuditLog).where(
                AuditLog.entity_id == booking_id,
                AuditLog.action == "complete_booking",
            )) is not None
            assert db.scalar(select(Task).where(
                Task.booking_id == booking_id,
                Task.completed.is_(False),
            )) is not None

        reopened = client.post(f"/api/bookings/{booking_id}/reopen-completed")
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["status"] == "confirmed"
        assert reopened.json()["workflow_state"]["completion"]["reopened_by"] == "mark@example.com"


def test_enquiry_cannot_be_mislabelled_as_completed_wedding():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json=wedding_payload(
            status="enquiry", event_date=date.today() + timedelta(days=200),
        )).json()
        response = client.post(f"/api/bookings/{booking['id']}/complete")
        assert response.status_code == 409
        assert "not a booked wedding" in response.json()["detail"]


def test_studio_style_assets_and_requested_wedding_tabs_are_loaded():
    root = Path(__file__).resolve().parents[1]
    index = (root / "app/static/index.html").read_text(encoding="utf-8")
    script = (root / "app/static/v830.js").read_text(encoding="utf-8")
    css = (root / "app/static/v830.css").read_text(encoding="utf-8")

    assert "/static/v830.css?v=studio-style-workspace-v8-30" in index
    assert "/static/v830.js?v=studio-style-workspace-v8-30" in index
    assert "STUDIO MOBILE WORKSPACE V8.30.1" in index
    assert "Upcoming weddings" in script
    assert "All bookings" in script
    assert "Past weddings awaiting completion" in script
    assert "Mark wedding complete" in script
    assert "/complete" in script and "/reopen-completed" in script
    assert "Conversation with" in script
    for label in ("Job", "Client", "INVOICES & PAYMENTS", "QUOTE", "AGREEMENT",
                  "QUESTIONNAIRES & TIMINGS", "FILES", "NOTES & TASKS"):
        assert label in script
    assert ".v830-job-board" in css
    assert ".v830-wedding-switcher" in css

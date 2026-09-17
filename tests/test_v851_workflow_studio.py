import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


TEST_ROOT = Path(__file__).parent
ROOT = TEST_ROOT.parent
DB_FILE = TEST_ROOT / "test-v851.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v851-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"


from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.main import app, run_due_reminders
from app.models import EmailLog, ReminderLog, SystemSetting, Task


def test_workflow_studio_preserves_defaults_and_can_queue_review_without_sending():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v851.db-journal").unlink(missing_ok=True)
    today = date.today()

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200

        studio = client.get("/api/communications/workflows")
        assert studio.status_code == 200, studio.text
        rules = {row["key"]: row for row in studio.json()["rules"]}
        assert rules["quote_followup_1"]["mode"] == "automatic"
        assert rules["quote_followup_1"]["days"] == 1
        assert rules["quote_followup_final"]["days"] == 9
        assert rules["booking_form_reminder"]["mode"] == "off"
        assert rules["contract_reminder"]["mode"] == "off"
        with SessionLocal() as db:
            assert db.get(SystemSetting, "workflow_studio_wbm") is None

        save_rules = {
            key: {
                "mode": row["mode"], "days": row["days"],
                **({"repeat_days": row["repeat_days"]} if row.get("repeatable") else {}),
            }
            for key, row in rules.items()
        }
        save_rules["quote_followup_1"] = {"mode": "review", "days": 2}
        saved = client.put("/api/communications/workflows", json={"rules": save_rules})
        assert saved.status_code == 200, saved.text

        booking = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "quoted",
            "title": "Workflow Review Couple",
            "client": {"first_name": "Review", "last_name": "Couple",
                       "partner_name": "Partner", "email": "review-v851@example.com"},
            "event_date": (today + timedelta(days=180)).isoformat(),
            "venue_or_project": "Workflow Venue", "quoted_total": 899,
            "deposit_amount": 100,
        })
        assert booking.status_code == 201, booking.text
        booking_id = booking.json()["id"]
        with SessionLocal() as db:
            db.add(EmailLog(
                booking_id=booking_id, template_key="quote",
                recipient="review-v851@example.com", subject="Your quote", status="sent",
                sent_at=datetime.combine(today - timedelta(days=2), time(10), tzinfo=timezone.utc),
            ))
            db.commit()
            result = run_due_reminders(db, today=today)
            assert result == {"sent": 0, "skipped": 0, "failed": 0, "awaiting_review": 1}
            reminder = db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == booking_id,
                ReminderLog.reminder_key == "quote_followup_1",
            ))
            assert reminder and reminder.status == "awaiting_review"
            assert db.scalar(select(Task.id).where(
                Task.workflow_key == f"workflow_email:{reminder.id}",
                Task.completed.is_(False),
            ))
            reminder_id = reminder.id

        queue = client.get("/api/communications/workflows")
        pending = queue.json()["pending_review"]
        assert any(row["id"] == reminder_id for row in pending)
        preview = client.get(f"/api/communications/workflows/review/{reminder_id}/preview")
        assert preview.status_code == 200, preview.text
        assert "Workflow Review Couple" == preview.json()["booking_title"]
        assert "Nothing" not in preview.json()["html"]

        skipped = client.post(f"/api/communications/workflows/review/{reminder_id}/skip")
        assert skipped.status_code == 200, skipped.text
        with SessionLocal() as db:
            assert db.get(ReminderLog, reminder_id).status == "skipped"
            assert db.scalar(select(Task.completed).where(
                Task.workflow_key == f"workflow_email:{reminder_id}"
            )) is True


def test_workflow_studio_rejects_unsafe_ordering_and_assets_are_loaded():
    index = (ROOT / "app" / "static" / "index.html").read_text()
    javascript = (ROOT / "app" / "static" / "v851.js").read_text()
    css = (ROOT / "app" / "static" / "v851.css").read_text()
    assert "custom-workflow-studio-v8-51" in index
    assert "Custom Workflow Studio" in javascript
    assert "Review first" in javascript
    assert "Task only" in javascript
    assert ".v851-studio" in css

import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
ROOT = TEST_ROOT.parent
DB_FILE = TEST_ROOT / "test-v852.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v852-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"


from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.main import app, run_due_reminders
from app.models import ReminderLog, Task


def _booking(client, title, email):
    result = client.post("/api/bookings", json={
        "brand": "wbm", "kind": "wedding", "status": "enquiry", "title": title,
        "client": {"first_name": title.split()[0], "last_name": "Client",
                   "partner_name": "Partner", "email": email},
        "event_date": (date.today() + timedelta(days=180)).isoformat(),
        "venue_or_project": "Builder Test Venue", "quoted_total": 899,
        "deposit_amount": 100,
    })
    assert result.status_code == 201, result.text
    return result.json()["id"]


def test_custom_workflow_is_draft_first_and_future_bookings_only_by_default():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v852.db-journal").unlink(missing_ok=True)
    today = date.today()

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        old_booking = _booking(client, "Old Couple", "old-v852@example.com")
        studio = client.get("/api/communications/workflows").json()
        assert studio["version"] == 2
        assert {item["key"] for item in studio["triggers"]} >= {
            "enquiry_created", "quote_sent", "quote_accepted", "wedding_date",
        }
        template_key = next(item["template_key"] for item in studio["available_templates"]
                            if item["template_key"] == "booking_link")

        created = client.post("/api/communications/workflows/custom", json={
            "name": "Welcome planning check-in", "trigger": "enquiry_created",
            "direction": "after", "days": 0, "mode": "review",
            "template_key": template_key,
        })
        assert created.status_code == 201, created.text
        workflow = created.json()
        assert workflow["status"] == "draft"

        with SessionLocal() as db:
            assert run_due_reminders(db, today=today) == {
                "sent": 0, "skipped": 0, "failed": 0,
            }

        activated = client.post(
            f"/api/communications/workflows/custom/{workflow['id']}/activate",
            json={"include_existing": False},
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["include_existing"] is False

        edit_while_live = client.put(
            f"/api/communications/workflows/custom/{workflow['id']}",
            json={"name": "Unsafe live edit", "trigger": "enquiry_created",
                  "direction": "after", "days": 1, "mode": "automatic",
                  "template_key": template_key},
        )
        assert edit_while_live.status_code == 409

        new_booking = _booking(client, "New Couple", "new-v852@example.com")
        with SessionLocal() as db:
            result = run_due_reminders(db, today=today)
            assert result == {"sent": 0, "skipped": 0, "failed": 0,
                              "awaiting_review": 1}
            reminders = db.scalars(select(ReminderLog).where(
                ReminderLog.reminder_key == f"custom:{workflow['id']}"
            )).all()
            assert [item.booking_id for item in reminders] == [new_booking]
            assert old_booking not in {item.booking_id for item in reminders}
            assert db.scalar(select(Task.id).where(
                Task.booking_id == new_booking,
                Task.workflow_key == f"workflow_email:{reminders[0].id}",
            ))

        queue = client.get("/api/communications/workflows").json()
        custom = next(item for item in queue["custom_workflows"] if item["id"] == workflow["id"])
        assert custom["status"] == "active"
        assert custom["trigger_label"] == "Enquiry received"
        assert custom["template_available"] is True


def test_custom_workflow_can_pause_edit_duplicate_and_delete_safely():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v852.db-journal").unlink(missing_ok=True)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        studio = client.get("/api/communications/workflows").json()
        template_key = studio["available_templates"][0]["template_key"]
        created = client.post("/api/communications/workflows/custom", json={
            "name": "Draft workflow", "trigger": "wedding_date", "direction": "before",
            "days": 14, "mode": "task", "template_key": template_key,
        }).json()
        activated = client.post(
            f"/api/communications/workflows/custom/{created['id']}/activate",
            json={"include_existing": True},
        )
        assert activated.status_code == 200
        assert client.delete(f"/api/communications/workflows/custom/{created['id']}").status_code == 409
        assert client.post(f"/api/communications/workflows/custom/{created['id']}/pause").status_code == 200
        edited = client.put(f"/api/communications/workflows/custom/{created['id']}", json={
            "name": "Edited safe workflow", "trigger": "wedding_date", "direction": "before",
            "days": 10, "mode": "review", "template_key": template_key,
        })
        assert edited.status_code == 200, edited.text
        copied = client.post(f"/api/communications/workflows/custom/{created['id']}/duplicate")
        assert copied.status_code == 201
        assert copied.json()["status"] == "draft"
        assert copied.json()["name"].startswith("Copy of")
        assert client.delete(
            f"/api/communications/workflows/custom/{copied.json()['id']}"
        ).status_code == 204


def test_v852_builder_is_visible_and_supports_inline_template_creation():
    index = (ROOT / "app" / "static" / "index.html").read_text()
    main = (ROOT / "app" / "main.py").read_text()
    backup = (ROOT / "app" / "backup.py").read_text()
    javascript = (ROOT / "app" / "static" / "v851.js").read_text()
    stylesheet = (ROOT / "app" / "static" / "v851.css").read_text()
    assert "BOOKINGSYSTEM2026 · COMPLETE V8.52" in index
    assert "custom-workflow-builder-v8-52" in index
    assert 'version="2.8.52"' in main
    assert 'BACKUP_BUILD = "2026.09.17-custom-workflow-builder-v8.52"' in backup
    assert "＋ Add workflow" in javascript
    assert "Create a new email template" in javascript
    assert "New bookings only" in javascript
    assert "Include current eligible bookings" in javascript
    assert "Preview &amp; test" in javascript
    assert ".v852-custom" in stylesheet

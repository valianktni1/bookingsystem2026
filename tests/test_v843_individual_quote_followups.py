import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


TEST_ROOT = Path(__file__).parent
ROOT = TEST_ROOT.parent
DB_FILE = TEST_ROOT / "test-v843.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v843-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"


from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main_module
from app.database import SessionLocal, engine
from app.main import app
from app.models import EmailLog, ReminderLog


def _create_booking(client, title, email):
    result = client.post("/api/bookings", json={
        "brand": "wbm", "kind": "wedding", "status": "quoted",
        "title": title,
        "client": {
            "first_name": title.split()[0], "last_name": "Client",
            "partner_name": "Partner", "email": email,
        },
        "event_date": (date.today() + timedelta(days=200)).isoformat(),
        "venue_or_project": "Test Venue", "quoted_total": 899,
        "deposit_amount": 100,
    })
    assert result.status_code == 201, result.text
    return result.json()["id"]


def test_each_quote_followup_can_be_paused_independently(monkeypatch):
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v843.db-journal").unlink(missing_ok=True)
    base = date.today()

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        skip_first = _create_booking(client, "Alice & Ben", "alice-v843@example.com")
        skip_final = _create_booking(client, "Cara & Dan", "cara-v843@example.com")
        with SessionLocal() as db:
            for booking_id, email in (
                (skip_first, "alice-v843@example.com"),
                (skip_final, "cara-v843@example.com"),
            ):
                db.add(EmailLog(
                    booking_id=booking_id, template_key="quote", recipient=email,
                    subject="Your quote", status="sent",
                    sent_at=datetime.combine(base, time(10, 0), tzinfo=timezone.utc),
                ))
            db.commit()

        first_pause = client.put(
            f"/api/bookings/{skip_first}/quote-followups/quote_followup_1",
            json={"paused": True},
        )
        final_pause = client.put(
            f"/api/bookings/{skip_final}/quote-followups/quote_followup_final",
            json={"paused": True},
        )
        assert first_pause.status_code == 200, first_pause.text
        assert final_pause.status_code == 200, final_pause.text

        first_controls = {
            row["reminder_key"]: row
            for row in client.get(f"/api/bookings/{skip_first}/portal").json()["quote_followups"]
        }
        final_controls = {
            row["reminder_key"]: row
            for row in client.get(f"/api/bookings/{skip_final}/portal").json()["quote_followups"]
        }
        assert first_controls["quote_followup_1"]["status"] == "paused"
        assert first_controls["quote_followup_final"]["status"] == "active"
        assert final_controls["quote_followup_1"]["status"] == "active"
        assert final_controls["quote_followup_final"]["status"] == "paused"

        resumed = client.put(
            f"/api/bookings/{skip_first}/quote-followups/quote_followup_1",
            json={"paused": False},
        )
        assert resumed.status_code == 200
        assert resumed.json()["paused"] is False
        assert client.put(
            f"/api/bookings/{skip_first}/quote-followups/quote_followup_1",
            json={"paused": True},
        ).status_code == 200

        class FrozenDate(date):
            current = base

            @classmethod
            def today(cls):
                return cls.current

        monkeypatch.setattr(main_module, "date", FrozenDate)
        monkeypatch.setattr(
            main_module, "send_template_email",
            lambda booking, profile, template, portal_url=None, **kwargs: (
                template.subject, template.body
            ),
        )

        FrozenDate.current = base + timedelta(days=1)
        with SessionLocal() as db:
            result = main_module.run_due_reminders(db)
            assert result["sent"] == 1
            assert not db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == skip_first,
                ReminderLog.reminder_key == "quote_followup_1",
            ))
            assert db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == skip_final,
                ReminderLog.reminder_key == "quote_followup_1",
            ))

        FrozenDate.current = base + timedelta(days=9)
        with SessionLocal() as db:
            result = main_module.run_due_reminders(db)
            assert result["sent"] == 1
            assert db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == skip_first,
                ReminderLog.reminder_key == "quote_followup_final",
            ))
            assert not db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == skip_final,
                ReminderLog.reminder_key == "quote_followup_final",
            ))


def test_followup_controls_are_clear_in_email_workspace_and_templates():
    script = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/v842.css").read_text(encoding="utf-8")
    bootstrap = (ROOT / "app/bootstrap.py").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")

    assert "Control this couple's two automatic checks" in script
    assert "Pause this follow-up" in script
    assert "Resume this follow-up" in script
    assert "Changing one switch never changes the other" in script
    assert ".v843-followups" in css
    assert "Quote follow-up - next day" in bootstrap
    assert "Quote follow-up - final check" in bootstrap
    assert '"quote_followup_1": ("automatic"' in main
    assert '"quote_followup_final": ("automatic"' in main


def teardown_module():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v843.db-journal").unlink(missing_ok=True)

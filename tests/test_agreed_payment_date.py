import os
from datetime import date, timedelta
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
from sqlalchemy import select

from app.database import SessionLocal, engine
import app.main as main_module
from app.main import app
from app.models import AuditLog, Booking, Invoice, ReminderLog


def test_agreed_payment_date_updates_invoice_pdf_data_and_reminders(monkeypatch):
    db_file = TEST_ROOT / "test.db"
    engine.dispose()
    db_file.unlink(missing_ok=True)
    (db_file.parent / "test.db-journal").unlink(missing_ok=True)
    today = date.today()
    wedding_day = today + timedelta(days=200)
    standard_due = wedding_day - timedelta(days=45)
    agreed_due = wedding_day - timedelta(days=26)

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        booking = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "confirmed",
            "title": "Payment Extension Couple",
            "client": {
                "first_name": "Sophie", "last_name": "Taylor",
                "partner_name": "James Taylor", "email": "extension@example.com",
            },
            "event_date": wedding_day.isoformat(),
            "venue_or_project": "Test Wedding Venue",
            "quoted_total": 899, "deposit_amount": 100,
            "deposit_paid_date": today.isoformat(),
            "balance_due_date": standard_due.isoformat(),
        })
        assert booking.status_code == 201
        booking_id = booking.json()["id"]
        invoice = client.post(f"/api/bookings/{booking_id}/invoices", json={
            "total": 899, "paid": 100, "issue_date": today.isoformat(),
            "deposit_due_date": today.isoformat(), "supply_date": wedding_day.isoformat(),
            "due_date": standard_due.isoformat(),
            "description": "Gold Package",
            "notes": f"Booking fee received. The remaining balance is due by {standard_due.strftime('%d %B %Y')}.",
        })
        assert invoice.status_code == 201
        invoice_id = invoice.json()["id"]

        with SessionLocal() as db:
            stored = db.get(Invoice, invoice_id)
            stored.payment_schedule = [
                {"label": "Booking fee", "amount": 100, "due_date": today.isoformat(), "status": "paid"},
                {"label": "Remaining balance", "amount": 799,
                 "due_date": standard_due.isoformat(), "status": "scheduled"},
            ]
            db.commit()

        changed = client.patch(f"/api/invoices/{invoice_id}/due-date", json={
            "due_date": agreed_due.isoformat(),
            "reason": "Extension agreed with the couple",
        })
        assert changed.status_code == 200
        result = changed.json()
        assert result["due_date"] == agreed_due.isoformat()
        assert result["payment_due_date"] == agreed_due.isoformat()
        assert result["standard_due_date"] == standard_due.isoformat()
        assert result["due_date_overridden"] is True
        assert result["payment_schedule"][-1]["due_date"] == agreed_due.isoformat()

        record = client.get(f"/api/bookings/{booking_id}").json()
        assert record["balance_due_date"] == agreed_due.isoformat()
        register_row = next(row for row in client.get("/api/invoices").json()
                            if row["id"] == invoice_id)
        assert register_row["due_date"] == agreed_due.isoformat()

        with SessionLocal() as db:
            stored = db.get(Invoice, invoice_id)
            assert stored.due_date == agreed_due
            assert agreed_due.strftime("%d %B %Y") in stored.notes
            audit = db.scalar(select(AuditLog).where(
                AuditLog.entity_id == booking_id,
                AuditLog.action == "change_invoice_due_date",
            ))
            assert audit.details["invoice_number"] == stored.number
            assert audit.details["reason"] == "Extension agreed with the couple"

        class FrozenDate(date):
            current = standard_due - timedelta(days=7)

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

        # The original 45-day date is no longer a reminder trigger.
        with SessionLocal() as db:
            assert main_module.run_due_reminders(db) == {
                "sent": 0, "skipped": 0, "failed": 0,
            }

        # The extension creates a new reminder schedule for this couple only.
        FrozenDate.current = agreed_due - timedelta(days=7)
        with SessionLocal() as db:
            assert main_module.run_due_reminders(db) == {
                "sent": 1, "skipped": 0, "failed": 0,
            }
            reminder = db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == booking_id,
                ReminderLog.reminder_key == "balance_due_7",
            ))
            assert reminder.scheduled_for == agreed_due - timedelta(days=7)

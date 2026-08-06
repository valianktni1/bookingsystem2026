import os
from datetime import date, datetime, time, timedelta, timezone
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
from app.models import Booking, EmailLog, Invoice, ReminderLog


def test_exact_simple_wedding_email_schedule(monkeypatch):
    db_file = TEST_ROOT / "test.db"
    engine.dispose()
    db_file.unlink(missing_ok=True)
    (db_file.parent / "test.db-journal").unlink(missing_ok=True)
    base = date.today()
    wedding_day = base + timedelta(days=200)

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        created = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "enquiry",
            "title": "Workflow Test Couple",
            "client": {
                "first_name": "Sophie", "last_name": "Taylor",
                "partner_name": "James Taylor", "email": "workflow@example.com",
            },
            "event_date": wedding_day.isoformat(),
            "venue_or_project": "Test Wedding Venue",
            "quoted_total": 0, "deposit_amount": 0,
        })
        assert created.status_code == 201
        booking_id = created.json()["id"]
        phone_call = next(task for task in created.json()["tasks"]
                          if task["workflow_key"] == "wbm_final_details_call")
        assert phone_call["title"] == "Finalise wedding details by phone"
        assert phone_call["due_at"].startswith(
            (wedding_day - timedelta(days=30)).isoformat()
        )

        # A successful initial quote email is the anchor for both quote follow-ups.
        with SessionLocal() as db:
            db.add(EmailLog(
                booking_id=booking_id, template_key="quote",
                recipient="workflow@example.com", subject="Your quote", status="sent",
                sent_at=datetime.combine(base, time(10, 0), tzinfo=timezone.utc),
            ))
            db.commit()

        class FrozenDate(date):
            current = base

            @classmethod
            def today(cls):
                return cls.current

        monkeypatch.setattr(main_module, "date", FrozenDate)
        monkeypatch.setattr(
            main_module, "send_template_email",
            lambda booking, profile, template, portal_url=None: (template.subject, template.body),
        )

        for reminder_day, reminder_key in (
            (base + timedelta(days=1), "quote_followup_1"),
            (base + timedelta(days=9), "quote_followup_final"),
        ):
            FrozenDate.current = reminder_day
            with SessionLocal() as db:
                assert main_module.run_due_reminders(db) == {
                    "sent": 1, "skipped": 0, "failed": 0,
                }
                assert db.scalar(select(ReminderLog).where(
                    ReminderLog.booking_id == booking_id,
                    ReminderLog.reminder_key == reminder_key,
                ))

        portal = client.post(f"/api/bookings/{booking_id}/portal", json={"expires_days": 365})
        token = portal.json()["url"].split("/client/")[1]
        gold = next(row for row in client.get("/api/catalog?brand=wbm").json()["packages"]
                    if row["code"] == "gold")
        FrozenDate.current = base
        accepted = client.post(f"/api/client/{token}/quote", json={
            "package_id": gold["id"], "addon_ids": [], "confirmed": True,
        })
        assert accepted.status_code == 201
        invoice_id = accepted.json()["invoice"]["id"]

        # No first payment: one booking-fee reminder on the next day.
        FrozenDate.current = base + timedelta(days=1)
        with SessionLocal() as db:
            assert main_module.run_due_reminders(db) == {
                "sent": 1, "skipped": 0, "failed": 0,
            }
            assert db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == booking_id,
                ReminderLog.reminder_key == "deposit_due_1",
            ))

        # Any first transfer secures the date while the remaining balance stays outstanding.
        payment = client.post(f"/api/invoices/{invoice_id}/payments", json={
            "amount": 50, "paid_date": (base + timedelta(days=1)).isoformat(),
            "payment_type": "bank_transfer", "reference": "WBM workflow test",
        })
        assert payment.status_code == 201
        assert client.get(f"/api/bookings/{booking_id}").json()["status"] == "confirmed"

        balance_due = wedding_day - timedelta(days=45)
        schedule = (
            (wedding_day - timedelta(days=120), "check_in_120"),
            (balance_due - timedelta(days=7), "balance_due_7"),
            (balance_due - timedelta(days=1), "balance_due_1"),
            (balance_due + timedelta(days=2), "balance_overdue_2"),
            (balance_due + timedelta(days=4), "balance_overdue_4"),
        )
        for reminder_day, reminder_key in schedule:
            FrozenDate.current = reminder_day
            with SessionLocal() as db:
                assert main_module.run_due_reminders(db) == {
                    "sent": 1, "skipped": 0, "failed": 0,
                }
                assert db.scalar(select(ReminderLog).where(
                    ReminderLog.booking_id == booking_id,
                    ReminderLog.reminder_key == reminder_key,
                ))

        # Thirty days before is Mark's private phone-call task, not a
        # second questionnaire or a client email.
        FrozenDate.current = wedding_day - timedelta(days=30)
        with SessionLocal() as db:
            assert main_module.run_due_reminders(db) == {
                "sent": 0, "skipped": 0, "failed": 0,
            }
            assert not db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == booking_id,
                ReminderLog.reminder_key == "final_questionnaire",
            ))

        # Repeating overdue reminders stop as soon as Mark marks the invoice paid.
        with SessionLocal() as db:
            invoice = db.get(Invoice, invoice_id)
            invoice.paid = invoice.total
            invoice.status = "paid"
            db.commit()
            FrozenDate.current = balance_due + timedelta(days=6)
            assert main_module.run_due_reminders(db) == {
                "sent": 0, "skipped": 0, "failed": 0,
            }
            booking = db.get(Booking, booking_id)
            assert booking.automation_suppressed is False

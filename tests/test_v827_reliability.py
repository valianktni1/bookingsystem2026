import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v827.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v827-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v827-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main_module
import app.google_calendar as calendar_module
from app.database import SessionLocal, engine
from app.main import app
from app.models import (Booking, Brand, Client, EmailLog, Invoice, LoginAttempt,
                        Payment, Quote, RecordKind, RecordStatus, ReminderLog)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v827.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v827.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def add_provisional(db, event_date: date) -> tuple[Booking, Invoice]:
    client = Client(first_name="Provisional", last_name="Couple", email="hold@example.com")
    db.add(client)
    db.flush()
    booking = Booking(
        brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.QUOTED,
        title="Provisional & Couple", client_id=client.id, event_date=event_date,
        venue_or_project="Test Hall", package_name="Silver Package 2",
        quoted_total=Decimal("699"), deposit_amount=Decimal("100"),
    )
    db.add(booking)
    db.flush()
    invoice = Invoice(
        booking_id=booking.id, brand=Brand.WBM, sequence=9701, number="WBM09701",
        issue_date=date.today(), deposit_due_date=date.today() + timedelta(days=1),
        total=Decimal("699"), paid=Decimal("0"), status="unpaid",
    )
    db.add(invoice)
    db.flush()
    db.add(Quote(
        booking_id=booking.id, status="accepted", invoice_id=invoice.id,
        total=Decimal("699"), deposit_amount=Decimal("100"),
        accepted_at=datetime.now(timezone.utc),
    ))
    db.commit()
    return booking, invoice


def test_payment_is_the_only_native_secured_date_and_deletion_reverses_it():
    reset_database()
    wedding_day = date.today() + timedelta(days=250)
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            booking, invoice = add_provisional(db, wedding_day)
            booking_id, invoice_id = booking.id, invoice.id

        assert client.get(
            f"/api/public/availability?date={wedding_day.isoformat()}"
        ).text == "Available"

        paid = client.post(f"/api/invoices/{invoice_id}/payments", json={
            "amount": 50, "paid_date": date.today().isoformat(),
            "payment_type": "bank_transfer", "reference": "Provisional 250",
        })
        assert paid.status_code == 201, paid.text
        assert client.get(f"/api/bookings/{booking_id}").json()["status"] == "confirmed"
        assert client.get(
            f"/api/public/availability?date={wedding_day.isoformat()}"
        ).text == "Booked"

        payment_id = paid.json()["payments"][0]["id"]
        removed = client.delete(f"/api/payments/{payment_id}")
        assert removed.status_code == 204, removed.text
        record = client.get(f"/api/bookings/{booking_id}").json()
        assert record["status"] == "quoted"
        assert record["deposit_paid_date"] is None
        assert client.get(
            f"/api/public/availability?date={wedding_day.isoformat()}"
        ).text == "Available"


def test_failed_reminder_is_durable_throttled_and_then_recovers(monkeypatch):
    reset_database()
    frozen_today = date(2027, 1, 1)

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return frozen_today

    monkeypatch.setattr(main_module, "date", FrozenDate)
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            couple = Client(first_name="Retry", last_name="Couple", email="retry@example.com")
            db.add(couple)
            db.flush()
            booking = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CONFIRMED,
                title="Retry & Couple", client_id=couple.id,
                event_date=frozen_today + timedelta(days=30),
                package_name="Silver Package 2", automation_suppressed=False,
            )
            db.add(booking)
            db.commit()
            booking_id = booking.id

        def fail_send(*_args, **_kwargs):
            raise RuntimeError("Temporary SMTP failure")

        monkeypatch.setattr(main_module, "send_booking_template_email", fail_send)
        with SessionLocal() as db:
            assert main_module.run_due_reminders(db) == {
                "sent": 0, "skipped": 0, "failed": 1,
            }
            reminder = db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == booking_id,
                ReminderLog.reminder_key == "check_in_30",
            ))
            assert reminder.status == "failed"
            assert reminder.retry_count == 1
            assert reminder.next_attempt_at is not None
            assert main_module.run_due_reminders(db) == {
                "sent": 0, "skipped": 1, "failed": 0,
            }
            reminder.next_attempt_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()

        monkeypatch.setattr(
            main_module, "send_booking_template_email",
            lambda *_args, **_kwargs: ("Final timings", "Exact rendered body"),
        )
        with SessionLocal() as db:
            assert main_module.run_due_reminders(db) == {
                "sent": 1, "skipped": 0, "failed": 0,
            }
            reminder = db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == booking_id,
                ReminderLog.reminder_key == "check_in_30",
            ))
            assert reminder.status == "sent"
            assert reminder.retry_count == 2
            assert reminder.error is None


def test_failed_exact_email_is_visible_and_manually_retryable(monkeypatch):
    reset_database()
    sent = []
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            couple = Client(first_name="Email", last_name="Couple", email="email@example.com")
            db.add(couple)
            db.flush()
            booking = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CONFIRMED,
                title="Email & Couple", client_id=couple.id,
                event_date=date.today() + timedelta(days=100),
            )
            db.add(booking)
            db.flush()
            failed = EmailLog(
                booking_id=booking.id, template_key="payment_received",
                recipient="email@example.com", subject="Payment received",
                body="This is the exact retained wording.", status="failed",
                error="Temporary SMTP failure",
            )
            db.add(failed)
            db.commit()
            failure_id = failed.id

        queue = client.get("/api/workflow-queues").json()["queues"]["communication_failures"]
        assert any(row["failure_id"] == failure_id and row["retryable"] for row in queue)

        monkeypatch.setattr(
            main_module, "send_rendered_email",
            lambda booking, profile, recipient, subject, body:
            sent.append((recipient, subject, body)),
        )
        retried = client.post(f"/api/communications/failures/email/{failure_id}/retry")
        assert retried.status_code == 200, retried.text
        assert sent == [("email@example.com", "Payment received", "This is the exact retained wording.")]
        assert all(
            row["failure_id"] != failure_id
            for row in client.get("/api/workflow-queues").json()["queues"]["communication_failures"]
        )


def test_login_throttling_and_security_headers_are_enforced():
    reset_database()
    with TestClient(app) as client:
        for _ in range(main_module.settings.login_max_failures):
            assert client.post("/api/auth/login", json={
                "email": "mark@example.com", "password": "wrong-password",
            }).status_code == 401
        blocked = client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        })
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
        with SessionLocal() as db:
            attempt = db.get(LoginAttempt, "mark@example.com")
            assert attempt.failed_count == main_module.settings.login_max_failures
            attempt.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        allowed = client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        })
        assert allowed.status_code == 200
        assert allowed.headers["x-frame-options"] == "DENY"
        assert allowed.headers["x-content-type-options"] == "nosniff"


def test_failed_google_calendar_work_is_retried_without_creating_a_duplicate(monkeypatch):
    reset_database()
    calls = []
    monkeypatch.setattr(calendar_module, "google_calendar_configured", lambda: True)
    monkeypatch.setattr(calendar_module, "_connection", lambda db: {
        "encrypted_refresh_token": "not-used", "calendar_id": "primary",
    })
    monkeypatch.setattr(calendar_module, "_access_token", lambda connection: "access-token")

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "stable-google-event"}

    def request(method, path, token, *, json=None):
        calls.append((method, path, json))
        return Response()

    monkeypatch.setattr(calendar_module, "_calendar_request", request)
    with TestClient(app):
        with SessionLocal() as db:
            couple = Client(first_name="Calendar", last_name="Retry", email="calendar@example.com")
            db.add(couple)
            db.flush()
            booking = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CONFIRMED,
                title="Calendar & Retry", client_id=couple.id,
                event_date=date.today() + timedelta(days=200),
                workflow_state={"google_calendar": {
                    "status": "error", "desired_action": "create",
                    "last_error": "Temporary Google outage",
                }},
            )
            db.add(booking)
            db.flush()
            invoice = Invoice(
                booking_id=booking.id, brand=Brand.WBM, sequence=9702,
                number="WBM09702", issue_date=date.today(), total=Decimal("699"),
                paid=Decimal("50"), status="part_paid",
            )
            db.add(invoice)
            db.flush()
            db.add(Payment(
                invoice_id=invoice.id, amount=Decimal("50"),
                paid_date=date.today(), payment_type="bank_transfer",
            ))
            db.commit()

            result = calendar_module.retry_pending_calendar_syncs(db)
            assert result == {"checked": 1, "synced": 1, "removed": 0, "failed": 0}
            assert len(calls) == 1
            assert calls[0][0] == "POST"
            refreshed = db.get(Booking, booking.id)
            assert refreshed.workflow_state["google_calendar"]["event_id"] == "stable-google-event"

            # A successful state is not selected again by the retry worker.
            assert calendar_module.retry_pending_calendar_syncs(db) == {
                "checked": 0, "synced": 0, "removed": 0, "failed": 0,
            }
            assert len(calls) == 1


def test_uncertain_calendar_create_is_removed_by_stable_id_after_cancellation(monkeypatch):
    reset_database()
    calls = []
    monkeypatch.setattr(calendar_module, "google_calendar_configured", lambda: True)
    monkeypatch.setattr(calendar_module, "_connection", lambda db: {
        "encrypted_refresh_token": "not-used", "calendar_id": "primary",
    })
    monkeypatch.setattr(calendar_module, "_access_token", lambda connection: "access-token")

    class Response:
        status_code = 204

        @staticmethod
        def json():
            return {}

    def request(method, path, token, *, json=None):
        calls.append((method, path))
        return Response()

    monkeypatch.setattr(calendar_module, "_calendar_request", request)
    with TestClient(app):
        with SessionLocal() as db:
            couple = Client(first_name="Cancelled", last_name="Retry", email="cancel@example.com")
            db.add(couple)
            db.flush()
            booking = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CANCELLED,
                title="Cancelled & Retry", client_id=couple.id,
                event_date=date.today() + timedelta(days=200),
                workflow_state={"google_calendar": {
                    "status": "error", "desired_action": "create",
                    "last_error": "Response was lost after create",
                }},
            )
            db.add(booking)
            db.commit()

            result = calendar_module.sync_booking_calendar_safely(db, booking)
            assert result["status"] == "removed"
            assert calls == [("DELETE", calls[0][1])]
            assert calendar_module._deterministic_event_id(booking) in calls[0][1]

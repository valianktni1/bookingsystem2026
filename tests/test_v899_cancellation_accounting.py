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
from app.main import app, run_due_reminders
from app.models import AuditLog, Booking, EmailLog, Invoice, Payment, RecordStatus, ReminderLog


def test_cancel_closes_only_unpaid_balance_and_refund_reduces_retained_income():
    db_file = TEST_ROOT / "test.db"
    engine.dispose()
    db_file.unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)
    today = date.today()
    wedding_day = today + timedelta(days=120)

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        booking = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "confirmed",
            "title": "Cancelled September Couple",
            "client": {
                "first_name": "Sophie", "last_name": "Taylor",
                "partner_name": "James Taylor", "email": "cancelled@example.com",
            },
            "event_date": wedding_day.isoformat(),
            "venue_or_project": "Test Wedding Venue",
            "quoted_total": 900, "deposit_amount": 100,
            "deposit_paid_date": today.isoformat(),
            "balance_due_date": (wedding_day - timedelta(days=45)).isoformat(),
        }).json()
        invoice = client.post(f"/api/bookings/{booking['id']}/invoices", json={
            "total": 900, "paid": 100, "issue_date": today.isoformat(),
            "deposit_due_date": today.isoformat(),
            "supply_date": wedding_day.isoformat(),
            "due_date": (wedding_day - timedelta(days=45)).isoformat(),
            "description": "Wedding package",
        }).json()
        portal = client.post(f"/api/bookings/{booking['id']}/portal", json={
            "expires_days": 365,
        }).json()
        token = portal["url"].split("/client/")[1]
        assert client.get(f"/api/client/{token}").status_code == 200
        assert client.get("/api/dashboard").json()["outstanding"] == 800

        cancelled = client.post(f"/api/bookings/{booking['id']}/cancel", json={
            "reason": "Couple cancelled their September wedding",
            "cancellation_date": today.isoformat(),
        })
        assert cancelled.status_code == 200
        assert cancelled.json()["unpaid_balance_closed"] == 800
        assert cancelled.json()["payments_retained"] == 100
        assert cancelled.json()["emails_sent"] == 0
        assert client.get(f"/api/client/{token}").status_code == 404
        assert client.post(f"/api/bookings/{booking['id']}/emails/send", json={
            "template_key": "booking_link",
        }).status_code == 409

        record = client.get(f"/api/bookings/{booking['id']}").json()
        assert record["status"] == "cancelled"
        assert record["automation_suppressed"] is True
        assert record["workflow_state"]["cancellation"]["reason"] == (
            "Couple cancelled their September wedding"
        )
        assert record["workflow_state"]["cancellation"]["emails_sent"] == 0
        closed_invoice = record["invoices"][0]
        assert closed_invoice["status"] == "cancelled"
        assert closed_invoice["balance"] == 0
        assert closed_invoice["paid"] == 100
        assert closed_invoice["cancellation_record"]["closed_balance"] == 800
        assert closed_invoice["cancellation_record"]["cancellation_date"] == today.isoformat()
        assert client.get("/api/dashboard").json()["outstanding"] == 0
        with SessionLocal() as db:
            assert run_due_reminders(db) == {"sent": 0, "skipped": 0, "failed": 0}

        refund = client.post(f"/api/invoices/{invoice['id']}/refunds", json={
            "amount": 40,
            "refund_date": today.isoformat(),
            "reference": "BANK-REFUND-1",
            "reason": "Partial deposit refund agreed with the couple",
        })
        assert refund.status_code == 201
        assert refund.json()["payments_retained"] == 60
        assert refund.json()["emails_sent"] == 0

        updated = client.get(f"/api/bookings/{booking['id']}").json()["invoices"][0]
        assert updated["gross_paid"] == 100
        assert updated["refunded"] == 40
        assert updated["paid"] == 60
        assert updated["balance"] == 0
        refund_payment = next(row for row in updated["payments"] if row["payment_type"] == "refund")
        assert refund_payment["amount"] == -40
        assert refund_payment["notes"] == "Partial deposit refund agreed with the couple"
        assert client.post(f"/api/invoices/{invoice['id']}/refunds", json={
            "amount": 61, "refund_date": today.isoformat(), "reason": "Too much",
        }).status_code == 422
        assert client.post(f"/api/invoices/{invoice['id']}/payments", json={
            "amount": 1, "paid_date": today.isoformat(), "payment_type": "bank_transfer",
        }).status_code == 409

        pdf = client.get(f"/api/invoices/{invoice['id']}/pdf")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")

        final_record = client.get(f"/api/bookings/{booking['id']}").json()
        refund_audit = next(
            row for row in final_record["activity"]
            if row["action"] == "record_cancellation_refund"
        )
        assert refund_audit["details"]["amount"] == 40
        assert refund_audit["details"]["emails_sent"] == 0


def test_cancellation_controls_are_visible_in_admin_interface():
    root = Path(__file__).resolve().parents[1]
    script = (root / "app/static/v82.js").read_text()
    stylesheet = (root / "app/static/v82.css").read_text()
    assert "Cancel & close balance" in script
    assert "Unpaid balance being closed" in script
    assert "Record refund" in script
    assert "No client email sent" in script
    assert "v899-cancelled-invoice" in stylesheet

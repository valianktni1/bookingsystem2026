import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


TEST_ROOT = Path(__file__).parent
DB_FILE = TEST_ROOT / "test-v848.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v848-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"


from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal, engine
import app.google_calendar as calendar_module
from app.main import _due_reminders, app
from app.models import AuditLog, Booking, EmailLog, Invoice, Payment, Quote


def reset_database():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v848.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com",
        "password": "SecureTestPassword!123",
    }).status_code == 200


def create_accepted_unpaid_booking(client):
    wedding_date = date.today() + timedelta(days=70)
    booking_response = client.post("/api/bookings", json={
        "brand": "wbm",
        "kind": "wedding",
        "status": "quoted",
        "title": "Exceptional Payment Couple",
        "client": {
            "first_name": "Exceptional",
            "last_name": "Couple",
            "partner_name": "Partner Couple",
            "email": "exception-v848@example.com",
        },
        "event_date": wedding_date.isoformat(),
        "venue_or_project": "Test Wedding Hall",
        "package_name": "Silver Package",
        "quoted_total": 699,
        "deposit_amount": 100,
    })
    assert booking_response.status_code == 201, booking_response.text
    booking = booking_response.json()
    original_due = wedding_date - timedelta(days=45)
    invoice_response = client.post(f"/api/bookings/{booking['id']}/invoices", json={
        "total": 699,
        "paid": 0,
        "issue_date": date.today().isoformat(),
        "deposit_due_date": (date.today() + timedelta(days=1)).isoformat(),
        "supply_date": wedding_date.isoformat(),
        "due_date": original_due.isoformat(),
        "description": "Silver wedding package",
        "notes": (
            f"Booking fee of £100.00 is due by "
            f"{(date.today() + timedelta(days=1)).strftime('%d %B %Y')}. "
            f"The remaining balance is due by {original_due.strftime('%d %B %Y')}."
        ),
    })
    assert invoice_response.status_code == 201, invoice_response.text
    invoice = invoice_response.json()
    with SessionLocal() as db:
        db.add(Quote(
            booking_id=booking["id"],
            invoice_id=invoice["id"],
            status="accepted",
            total=699,
            deposit_amount=100,
            line_items=[{"type": "package", "name": "Silver Package", "total": 699}],
            accepted_at=datetime.now(timezone.utc),
        ))
        db.commit()
    return booking, invoice, wedding_date, original_due


def test_secure_without_payment_is_truthful_audited_and_reversible():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking, invoice, wedding_date, original_due = create_accepted_unpaid_booking(client)

        wrong_phrase = client.post(
            f"/api/bookings/{booking['id']}/payment-arrangement",
            json={
                "agreed_payment_date": wedding_date.isoformat(),
                "reason": "Payment on arrival agreed in writing",
                "pause_payment_reminders": True,
                "confirmation": "YES",
            },
        )
        assert wrong_phrase.status_code == 422

        secured = client.post(
            f"/api/bookings/{booking['id']}/payment-arrangement",
            json={
                "agreed_payment_date": wedding_date.isoformat(),
                "reason": "Payment on arrival agreed in writing after a scam",
                "pause_payment_reminders": True,
                "confirmation": "SECURE WITHOUT PAYMENT",
            },
        )
        assert secured.status_code == 200, secured.text
        assert secured.json()["payment_arrangement"]["active"] is True
        assert "no payment was recorded" in secured.json()["message"].lower()

        record = client.get(f"/api/bookings/{booking['id']}").json()
        assert record["status"] == "confirmed"
        assert record["deposit_paid_date"] is None
        assert record["payment_arrangement"]["active"] is True
        arranged_invoice = next(row for row in record["invoices"] if row["id"] == invoice["id"])
        assert arranged_invoice["deposit_due_date"] == wedding_date.isoformat()
        assert arranged_invoice["due_date"] == wedding_date.isoformat()
        assert "no payment has yet been received" in arranged_invoice["notes"].lower()
        assert client.get(
            f"/api/public/availability?date={wedding_date.isoformat()}"
        ).text == "Booked"

        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Payment).join(
                Invoice, Invoice.id == Payment.invoice_id
            ).where(Invoice.booking_id == booking["id"])) == 0
            assert db.scalar(select(func.count()).select_from(EmailLog).where(
                EmailLog.booking_id == booking["id"]
            )) == 0
            row = db.get(Booking, booking["id"])
            assert calendar_module._should_have_event(db, row) is True
            assert (row.workflow_state or {})["google_calendar"]["status"] == "pending"
            assert _due_reminders(db, row, wedding_date) == []
            audit_row = db.scalar(select(AuditLog).where(
                AuditLog.entity_id == booking["id"],
                AuditLog.action == "secure_without_payment",
            ))
            assert audit_row is not None
            assert audit_row.details["payment_record_created"] is False

        removed = client.request(
            "DELETE",
            f"/api/bookings/{booking['id']}/payment-arrangement",
            json={
                "reason": "The special arrangement was cancelled",
                "confirmation": "REMOVE PAYMENT ARRANGEMENT",
            },
        )
        assert removed.status_code == 200, removed.text
        restored = client.get(f"/api/bookings/{booking['id']}").json()
        assert restored["status"] == "quoted"
        assert restored["payment_arrangement"]["active"] is False
        restored_invoice = next(row for row in restored["invoices"] if row["id"] == invoice["id"])
        assert restored_invoice["deposit_due_date"] == (date.today() + timedelta(days=1)).isoformat()
        assert restored_invoice["due_date"] == original_due.isoformat()
        assert client.get(
            f"/api/public/availability?date={wedding_date.isoformat()}"
        ).text == "Available"


def test_genuine_payment_completes_and_deleted_payment_reactivates_arrangement():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking, invoice, wedding_date, _ = create_accepted_unpaid_booking(client)
        assert client.post(
            f"/api/bookings/{booking['id']}/payment-arrangement",
            json={
                "agreed_payment_date": wedding_date.isoformat(),
                "reason": "Payment on the wedding day agreed in writing",
                "pause_payment_reminders": True,
                "confirmation": "SECURE WITHOUT PAYMENT",
            },
        ).status_code == 200

        paid = client.post(f"/api/invoices/{invoice['id']}/payments", json={
            "amount": 100,
            "paid_date": date.today().isoformat(),
            "payment_type": "bank_transfer",
            "reference": "V848-REAL-PAYMENT",
        })
        assert paid.status_code == 201, paid.text
        after_payment = client.get(f"/api/bookings/{booking['id']}").json()
        assert after_payment["payment_arrangement"]["active"] is False
        assert after_payment["payment_arrangement"]["status"] == "completed_by_payment"
        assert after_payment["deposit_paid_date"] == date.today().isoformat()

        payment_id = paid.json()["payments"][0]["id"]
        deleted = client.delete(f"/api/payments/{payment_id}")
        assert deleted.status_code == 204, deleted.text
        after_delete = client.get(f"/api/bookings/{booking['id']}").json()
        assert after_delete["status"] == "confirmed"
        assert after_delete["deposit_paid_date"] is None
        assert after_delete["payment_arrangement"]["active"] is True
        assert client.get(
            f"/api/public/availability?date={wedding_date.isoformat()}"
        ).text == "Booked"


def test_payment_reminders_can_be_kept_active_around_the_agreed_date():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking, _, _, _ = create_accepted_unpaid_booking(client)
        agreed_date = date.today() + timedelta(days=7)
        assert client.post(
            f"/api/bookings/{booking['id']}/payment-arrangement",
            json={
                "agreed_payment_date": agreed_date.isoformat(),
                "reason": "A later payment date was agreed in writing",
                "pause_payment_reminders": False,
                "confirmation": "SECURE WITHOUT PAYMENT",
            },
        ).status_code == 200
        with SessionLocal() as db:
            row = db.get(Booking, booking["id"])
            reminders = _due_reminders(db, row, date.today())
            assert ("balance_due_7", date.today()) in reminders
            assert all(key != "deposit_due_1" for key, _ in reminders)


def test_v848_interface_exposes_clear_mobile_safe_controls():
    root = Path(__file__).parents[1]
    index = (root / "app/static/index.html").read_text(encoding="utf-8")
    script = (root / "app/static/v848.js").read_text(encoding="utf-8")
    stylesheet = (root / "app/static/v848.css").read_text(encoding="utf-8")
    release = (root / "RELEASE-NOTES-V8.48.md").read_text(encoding="utf-8")
    assert "BOOKINGSYSTEM2026 · COMPLETE V8.52" in index
    assert "/static/v848.js?v=payment-arrangement-v8-48" in index
    assert "/static/v848.css?v=payment-arrangement-v8-48" in index
    assert "Secure date without payment" in script
    assert "SECURE WITHOUT PAYMENT" in script
    assert "No payment will be recorded" in script
    assert "Pause automatic payment reminders" in script
    assert "@media(max-width:600px)" in stylesheet
    assert "No fake deposit or Payment row is created" in release

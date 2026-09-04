import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import fitz
from sqlalchemy import select


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v834.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v834-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v834-test-session-secret-at-least-32-characters"
os.environ["ACCOUNTS_INTEGRATION_ENABLED"] = "false"

from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.final_timings import booking_coverage_allowance
from app.main import app
from app.models import (AuditLog, Booking, Brand, Client, EmailLog, Invoice,
                        Payment, Quote, RecordKind, RecordStatus)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v834.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v834.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def create_accepted_invoice(*, total=Decimal("899.00"), paid=Decimal("0"),
                            status="unpaid", manual_items=None, legacy=False):
    with SessionLocal() as db:
        couple = Client(first_name="Sophie", last_name="Taylor", partner_name="James",
                        email="sophie@example.com")
        db.add(couple)
        db.flush()
        booking = Booking(
            brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CONFIRMED,
            title="Sophie & James", client_id=couple.id, event_date=date(2027, 8, 21),
            venue_or_project="Test Barn", package_name="Gold Package",
            quoted_total=total, deposit_amount=Decimal("200.00"),
            legacy_source="studio_ninja" if legacy else None,
        )
        db.add(booking)
        db.flush()
        lines = [{
            "type": "package", "code": "gold", "name": "Gold Package",
            "description": "Full-day photography and highlight video",
            "quantity": 1, "unit_price": 899.0, "total": 899.0,
        }, *(manual_items or [])]
        invoice = Invoice(
            booking_id=booking.id, brand=Brand.WBM, sequence=83401,
            number="WBM83401", issue_date=date(2026, 9, 3),
            deposit_due_date=date(2026, 9, 4),
            due_date=booking.event_date - timedelta(days=45), supply_date=booking.event_date,
            description="Gold Package", total=total, paid=paid, status=status,
            line_items=lines,
            payment_schedule=[
                {"key": "booking_fee", "label": "Booking fee", "amount": 200.0,
                 "due_date": "2026-09-04", "status": "scheduled"},
                {"key": "final_45", "label": "Remaining balance",
                 "amount": float(total - Decimal("200")),
                 "due_date": (booking.event_date - timedelta(days=45)).isoformat(),
                 "status": "scheduled"},
            ],
        )
        db.add(invoice)
        db.flush()
        quote = Quote(
            booking_id=booking.id, status="accepted", invoice_id=invoice.id,
            line_items=lines, total=total, deposit_amount=Decimal("200"),
        )
        db.add(quote)
        if paid > 0:
            db.add(Payment(invoice_id=invoice.id, amount=paid,
                           paid_date=date(2026, 9, 3), payment_type="bank_transfer"))
        db.commit()
        return booking.id, invoice.id, invoice.number


def amendment_payload(total, paid, items):
    return {
        "additional_items": items,
        "reason": "Couple asked for this to appear on their invoice",
        "expected_total": float(total),
        "expected_paid": float(paid),
    }


def test_free_hour_updates_same_invoice_quote_portal_pdf_and_coverage_without_email():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking_id, invoice_id, number = create_accepted_invoice()
        portal_link = client.post(
            f"/api/bookings/{booking_id}/portal", json={"expires_days": 90}
        )
        assert portal_link.status_code == 201
        token = portal_link.json()["url"].split("/client/")[1]
        response = client.put(
            f"/api/invoices/{invoice_id}/amendment",
            json=amendment_payload(Decimal("899"), Decimal("0"), [{
                "name": "Complimentary extra hour",
                "description": "One additional hour at no extra charge.",
                "quantity": 1,
                "unit_price": 0,
            }]),
        )
        assert response.status_code == 200, response.text
        amended = response.json()
        assert amended["number"] == number
        assert amended["total"] == 899.0
        assert amended["balance"] == 899.0
        assert amended["amendment_allowed"] is True
        assert amended["line_items"][-1]["manual_amendment"] is True

        record = client.get(f"/api/bookings/{booking_id}").json()
        assert record["quoted_total"] == 899.0
        assert record["invoices"][0]["line_items"][-1]["name"] == "Complimentary extra hour"
        portal = client.get(f"/api/bookings/{booking_id}/portal").json()
        assert portal["quote"]["line_items"][-1]["name"] == "Complimentary extra hour"
        public_portal = client.get(f"/api/client/{token}").json()
        assert public_portal["quote"]["line_items"][-1]["name"] == "Complimentary extra hour"
        assert public_portal["invoices"][0]["line_items"][-1]["name"] == "Complimentary extra hour"

        pdf = client.get(f"/api/invoices/{invoice_id}/pdf")
        assert pdf.status_code == 200
        document = fitz.open(stream=pdf.content, filetype="pdf")
        text = "\n".join(page.get_text() for page in document)
        assert "Complimentary extra hour" in text

        with SessionLocal() as db:
            booking = db.get(Booking, booking_id)
            assert booking_coverage_allowance(db, booking)["extra_hours"] == 1
            audit = db.scalar(select(AuditLog).where(
                AuditLog.action == "amend_accepted_invoice",
                AuditLog.entity_id == booking_id,
            ))
            assert audit.details["invoice_number_changed"] is False
            assert audit.details["emails_sent"] == 0
            assert db.scalar(select(EmailLog).where(EmailLog.booking_id == booking_id)) is None


def test_part_paid_invoice_can_add_charge_and_preserves_number_payment_and_agreed_due_date():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking_id, invoice_id, number = create_accepted_invoice(
            paid=Decimal("200"), status="part_paid"
        )
        agreed_due = date(2027, 7, 1)
        with SessionLocal() as db:
            invoice = db.get(Invoice, invoice_id)
            invoice.due_date = agreed_due
            invoice.booking.balance_due_date = agreed_due
            db.commit()

        response = client.put(
            f"/api/invoices/{invoice_id}/amendment",
            json=amendment_payload(Decimal("899"), Decimal("200"), [{
                "name": "Additional album", "quantity": 1, "unit_price": 100,
            }]),
        )
        assert response.status_code == 200, response.text
        amended = response.json()
        assert amended["number"] == number
        assert amended["total"] == 999.0
        assert amended["paid"] == 200.0
        assert amended["balance"] == 799.0
        assert amended["status"] == "part_paid"
        assert amended["due_date"] == agreed_due.isoformat()
        assert amended["payment_schedule"][-1]["amount"] == 799.0
        assert amended["payment_schedule"][-1]["due_date"] == agreed_due.isoformat()

        with SessionLocal() as db:
            quote = db.scalar(select(Quote).where(Quote.invoice_id == invoice_id))
            booking = db.get(Booking, booking_id)
            assert quote.total == Decimal("999.00")
            assert booking.quoted_total == Decimal("999.00")


def test_paid_in_full_invoice_is_locked_and_explains_lock_in_record():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking_id, invoice_id, _ = create_accepted_invoice(
            total=Decimal("899"), paid=Decimal("899"), status="paid"
        )
        response = client.put(
            f"/api/invoices/{invoice_id}/amendment",
            json=amendment_payload(Decimal("899"), Decimal("899"), [{
                "name": "Complimentary extra hour", "quantity": 1, "unit_price": 0,
            }]),
        )
        assert response.status_code == 409
        assert "paid in full" in response.json()["detail"].lower()
        invoice = client.get(f"/api/bookings/{booking_id}").json()["invoices"][0]
        assert invoice["accepted_quote_invoice"] is True
        assert invoice["amendment_allowed"] is False
        assert invoice["amendment_lock_reason"] == "Paid in full"


def test_accepted_financial_summary_cannot_be_changed_around_the_invoice_editor():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking_id, _, _ = create_accepted_invoice()
        response = client.patch(f"/api/bookings/{booking_id}", json={
            "quoted_total": 999,
        })
        assert response.status_code == 409
        assert "Use Amend invoice in Payments" in response.json()["detail"]
        assert client.get(f"/api/bookings/{booking_id}").json()["quoted_total"] == 899.0


def test_stale_editor_and_reduction_below_amount_paid_are_blocked():
    reset_database()
    manual = [{
        "type": "addon", "code": "manual_amendment_1", "name": "Extra album",
        "description": "", "quantity": 1, "unit_price": 100.0, "total": 100.0,
        "required": True, "manual_amendment": True,
    }]
    with TestClient(app) as client:
        login(client)
        _, invoice_id, _ = create_accepted_invoice(
            total=Decimal("999"), paid=Decimal("950"), status="part_paid", manual_items=manual
        )
        stale = client.put(
            f"/api/invoices/{invoice_id}/amendment",
            json=amendment_payload(Decimal("998"), Decimal("950"), manual),
        )
        assert stale.status_code == 409
        assert "changed while the editor was open" in stale.json()["detail"]

        too_low = client.put(
            f"/api/invoices/{invoice_id}/amendment",
            json=amendment_payload(Decimal("999"), Decimal("950"), []),
        )
        assert too_low.status_code == 422
        assert "cannot be less" in too_low.json()["detail"]


def test_imported_invoice_cannot_be_amended_and_frontend_has_protected_controls():
    reset_database()
    with TestClient(app) as client:
        login(client)
        _, invoice_id, _ = create_accepted_invoice(legacy=True)
        response = client.put(
            f"/api/invoices/{invoice_id}/amendment",
            json=amendment_payload(Decimal("899"), Decimal("0"), []),
        )
        assert response.status_code == 409

    root = Path(__file__).parents[1]
    js = (root / "app/static/v834.js").read_text()
    css = (root / "app/static/v834.css").read_text()
    index = (root / "app/static/index.html").read_text()
    assert "✎ Amend invoice" in js
    assert "Complimentary extra hour" in js
    assert "expected_total" in js and "expected_paid" in js
    assert "Paid in full · editing locked" in js
    assert "No email is sent" in js
    assert "Protected by the accepted invoice" in js
    assert "@media(max-width:700px)" in css
    assert "/static/v834.js?v=protected-invoice-amendments-v8-34" in index
    assert "/static/v834.css?v=protected-invoice-amendments-v8-34" in index


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v834.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v834.db-journal").unlink(missing_ok=True)

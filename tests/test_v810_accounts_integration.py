import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"

from app.accounts_integration import build_invoice_payload
from app.models import Booking, Brand, Client, Invoice, Payment, RecordKind, RecordStatus


def linked_invoice(wedding_date=date(2026, 9, 12)):
    booking = Booking(
        id="booking-123", brand=Brand.WBM, kind=RecordKind.WEDDING,
        status=RecordStatus.CANCELLED, title="Sophie & James",
        event_date=wedding_date, venue_or_project="Test Venue",
        package_name="Gold", quoted_total=Decimal("899"),
        workflow_state={"cancellation": {
            "cancellation_date": "2026-08-17",
            "reason": "Wedding cancelled and the deposit was returned",
        }},
    )
    booking.client = Client(
        id="client-123", first_name="Sophie", last_name="Taylor",
        partner_name="James", email="couple@example.com",
    )
    invoice = Invoice(
        id="invoice-123", booking_id=booking.id, booking=booking,
        brand=Brand.WBM, sequence=2059, number="WBM02059",
        issue_date=date(2026, 8, 14), due_date=date(2026, 7, 29),
        description="Gold wedding package", total=Decimal("899"),
        paid=Decimal("0"), status="cancelled",
        line_items=[{"name": "Gold package", "amount": 899}],
    )
    invoice.payments = [
        Payment(id="payment-1", invoice_id=invoice.id, amount=Decimal("100"),
                paid_date=date(2026, 8, 14), payment_type="bank_transfer"),
        Payment(id="refund-1", invoice_id=invoice.id, amount=Decimal("-100"),
                paid_date=date(2026, 8, 17), payment_type="refund"),
    ]
    return invoice


def test_payload_preserves_number_cancellation_and_signed_refund():
    payload, digest = build_invoice_payload(linked_invoice())
    assert payload["invoice_number"] == "WBM02059"
    assert payload["brand"] == "wbm"
    assert payload["record_kind"] == "wedding"
    assert payload["cancellation_date"] == "2026-08-17"
    assert payload["payments"][0]["amount"] == 100
    assert payload["payments"][1]["amount"] == -100
    assert payload["event_id"].endswith(digest[:32])


def test_payload_revision_is_deterministic_and_changes_with_financial_state():
    invoice = linked_invoice()
    first, first_hash = build_invoice_payload(invoice)
    second, second_hash = build_invoice_payload(invoice)
    assert first == second
    assert first_hash == second_hash
    invoice.payments[1].amount = Decimal("-50")
    changed, changed_hash = build_invoice_payload(invoice)
    assert changed_hash != first_hash
    assert changed["event_id"] != first["event_id"]


def test_out_of_scope_old_wedding_without_recent_payment_is_rejected():
    invoice = linked_invoice(date(2024, 9, 12))
    for payment in invoice.payments:
        payment.paid_date = date(2024, 8, 17)
    try:
        build_invoice_payload(invoice)
    except ValueError as error:
        assert str(error) == "before_2025_26_scope"
    else:
        raise AssertionError("Out-of-scope wedding was accepted")


def test_admin_interface_exposes_controlled_first_sync():
    root = Path(__file__).resolve().parents[1]
    script = (root / "app/static/v810.js").read_text()
    assert "SYNC ELIGIBLE WEDDING INVOICES" in script
    assert "No client emails" in script
    assert "Check connection" in script

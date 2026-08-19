import os
from datetime import date
from decimal import Decimal
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "payment-reference-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "payment-reference-test-secret-at-least-32-characters"
os.environ["INVOICE_START"] = "2000"

import pymupdf
from fastapi.testclient import TestClient

from app.database import engine
from app.email_service import _body_html, _plain_body, template_values
from app.main import app
from app.models import Booking, Brand, BusinessProfile, Client, Invoice, RecordKind, RecordStatus
from app.pdf import invoice_pdf
from app.services import payment_reference


def wedding(title="Beth Nixon & Stuart Turner", first="Beth", partner="Stuart Turner"):
    client = Client(first_name=first, last_name="Nixon", partner_name=partner,
                    email="couple@example.com")
    booking = Booking(
        brand=Brand.WBM,
        kind=RecordKind.WEDDING,
        status=RecordStatus.ENQUIRY,
        title=title,
        client=client,
        event_date=date(2027, 5, 15),
        venue_or_project="Test Hall",
        quoted_total=Decimal("899"),
        deposit_amount=Decimal("100"),
    )
    return booking


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)


def test_reference_uses_both_first_names_and_ddmmyy():
    assert payment_reference(wedding(), "WBM01205") == "BETHSTUART150527"


def test_reference_is_bank_safe_and_keeps_both_long_names():
    result = payment_reference(
        wedding("Alexandria Smith & Christopher Jones", "Alexandria", "Christopher Jones"),
        "WBM01205",
    )
    assert result == "ALEXANCHRIST150527"
    assert len(result) == 18
    assert result.isalnum() and result == result.upper()


def test_imported_record_retains_invoice_number_fallback():
    booking = wedding()
    booking.legacy_source = "studio_ninja"
    assert payment_reference(booking, "WBM01706") == "WBM01706"


def test_email_value_and_bold_rendering_are_safe():
    booking = wedding()
    profile = BusinessProfile(
        brand=Brand.WBM,
        display_name="Weddings By Mark",
        legal_name="Mark Adam Powell",
        invoice_prefix="WBM",
        bank_details={},
    )
    values = template_values(booking, profile)
    assert values["payment_reference"] == "BETHSTUART150527"
    html = _body_html("Payment reference: **BETHSTUART150527**")
    assert '<strong style="font-weight:800' in html
    assert "**" not in html
    assert _plain_body("Payment reference: **BETHSTUART150527**") == (
        "Payment reference: BETHSTUART150527"
    )


def test_invoice_pdf_prints_the_couple_reference_in_bold():
    booking = wedding()
    invoice = Invoice(
        booking=booking,
        brand=Brand.WBM,
        sequence=1205,
        number="WBM01205",
        issue_date=date(2026, 8, 19),
        deposit_due_date=date(2026, 8, 20),
        supply_date=booking.event_date,
        due_date=date(2027, 3, 31),
        description="Gold Package",
        total=Decimal("899"),
        paid=Decimal("0"),
        status="unpaid",
        payments=[],
    )
    profile = BusinessProfile(
        brand=Brand.WBM,
        display_name="Weddings By Mark",
        legal_name="Mark Adam Powell",
        invoice_prefix="WBM",
        bank_details={"account_name": "Mark Adam Powell", "sort_code": "04-06-05",
                      "account_number": "20315075"},
    )
    content = invoice_pdf(invoice, profile)
    with pymupdf.open(stream=content, filetype="pdf") as document:
        text = "\n".join(page.get_text() for page in document)
    assert "PAYMENT REFERENCE: BETHSTUART150527" in text
    assert "Please use BETHSTUART150527" in text


def test_public_quote_form_receives_the_same_reference():
    reset_database()
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        created = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "enquiry",
            "title": "Beth Nixon & Stuart Turner",
            "client": {"first_name": "Beth", "last_name": "Nixon",
                       "partner_name": "Stuart Turner", "email": "couple@example.com"},
            "event_date": "2027-05-15", "venue_or_project": "Test Hall",
            "quoted_total": 899, "deposit_amount": 100,
        })
        assert created.status_code == 201, created.text
        booking_id = created.json()["id"]
        portal = client.post(f"/api/bookings/{booking_id}/portal", json={"expires_days": 365})
        token = portal.json()["url"].split("/client/")[1]
        public = client.get(f"/api/client/{token}")
        assert public.status_code == 200
        assert public.json()["record"]["payment_reference"] == "BETHSTUART150527"


def test_client_quote_and_invoice_panels_highlight_the_reference():
    source = (TEST_ROOT.parent / "app" / "static" / "client.js").read_text()
    styles = (TEST_ROOT.parent / "app" / "static" / "quote.css").read_text()
    assert "YOUR BANK-TRANSFER PAYMENT REFERENCE" in source
    assert "data.record.payment_reference" in source
    assert ".quote-payment-reference strong" in styles

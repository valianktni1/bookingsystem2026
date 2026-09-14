from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_v834_invoice_amendments import (
    app,
    create_accepted_invoice,
    login,
    reset_database,
)


ROOT = Path(__file__).resolve().parents[1]


def test_invoice_and_receipt_downloads_use_couple_date_and_number():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking_id, invoice_id, _ = create_accepted_invoice(
            paid=Decimal("200.00"), status="part_paid"
        )
        invoice_name = "Sophie-and-James-21-August-2027-WBM83401-Invoice.pdf"
        receipt_name = "Sophie-and-James-21-August-2027-WBM83401-Receipt.pdf"

        invoice = client.get(f"/api/invoices/{invoice_id}/pdf")
        assert invoice.status_code == 200
        assert invoice.headers["content-disposition"] == (
            f'attachment; filename="{invoice_name}"'
        )
        inline = client.get(f"/api/invoices/{invoice_id}/pdf?inline=true")
        assert inline.headers["content-disposition"] == (
            f'inline; filename="{invoice_name}"'
        )
        receipt = client.get(f"/api/invoices/{invoice_id}/receipt.pdf")
        assert receipt.headers["content-disposition"] == (
            f'attachment; filename="{receipt_name}"'
        )

        portal = client.post(
            f"/api/bookings/{booking_id}/portal", json={"expires_days": 90}
        )
        assert portal.status_code == 201
        token = portal.json()["url"].split("/client/")[1]
        public_invoice = client.get(
            f"/api/client/{token}/invoices/{invoice_id}/invoice.pdf"
        )
        assert public_invoice.headers["content-disposition"] == (
            f'attachment; filename="{invoice_name}"'
        )
        public_receipt = client.get(
            f"/api/client/{token}/invoices/{invoice_id}/receipt.pdf"
        )
        assert public_receipt.headers["content-disposition"] == (
            f'attachment; filename="{receipt_name}"'
        )


def test_secure_preview_keeps_a_real_filename_on_mobile_and_download():
    script = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'href="${attr(previewUrl)}" target="_blank"' in script
    assert 'href="${attr(downloadUrl)}" download="${attr(filename)}"' in script
    assert 'url.searchParams.get("inline")==="true"' in script
    assert 'pdfDownloadFilename(response' in script
    assert 'response.headers.get("content-disposition")' in script


def test_filename_parts_are_safe_and_never_expose_internal_ids():
    from app.main import invoice_download_filename
    from app.models import Booking, Brand, Invoice, RecordKind

    booking = Booking(
        brand=Brand.WBM,
        kind=RecordKind.WEDDING,
        title='Zo\u00eb & Sam / "Summer"',
        event_date=date(2028, 6, 3),
    )
    invoice = Invoice(
        booking=booking,
        brand=Brand.WBM,
        number="WBM02519",
        issue_date=date(2026, 9, 14),
    )

    assert invoice_download_filename(invoice) == (
        "Zoe-and-Sam-Summer-03-June-2028-WBM02519-Invoice.pdf"
    )

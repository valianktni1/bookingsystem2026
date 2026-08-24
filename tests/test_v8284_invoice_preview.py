from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_static(name: str) -> str:
    return (ROOT / "app" / "static" / name).read_text(encoding="utf-8")


def test_every_invoice_card_has_preview_and_separate_download():
    script = read_static("v82.js")

    assert 'data-preview-invoice="${i.id}"' in script
    assert '>View invoice</button>' in script
    assert '>Download PDF</a>' in script
    assert "/pdf?inline=true" in script
    assert "showPdfPreview(`Invoice ${button.dataset.invoiceNumber}`" in script


def test_invoice_register_also_opens_in_screen():
    script = read_static("v82.js")

    assert 'data-register-preview-invoice="${i.id}"' in script
    assert "button.dataset.registerPreviewInvoice" in script


def test_final_call_pack_includes_direct_invoice_access():
    script = read_static("v823.js")
    css = read_static("v823.css")
    index = read_static("index.html")

    assert "Open what the couple actually booked" in script
    assert 'data-final-call-invoice="${invoice.id}"' in script
    assert "button.dataset.finalCallInvoice" in script
    assert ".v823-invoice-reference" in css
    assert "/static/v823.js?v=invoice-preview-v8-28-4" in index
    assert "/static/v82.js?v=invoice-preview-v8-28-4" in index

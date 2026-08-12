from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_interface_displays_retained_invoice_void_reason():
    script = (ROOT / "app/static/v82.js").read_text()
    stylesheet = (ROOT / "app/static/v82.css").read_text()
    assert "REASON RECORDED WHEN VOIDED" in script
    assert "View void reason" in script
    assert "data-v82-register-reason" in script
    assert "v8982-void-reason" in stylesheet

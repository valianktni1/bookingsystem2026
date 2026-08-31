from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_complete_timings_popup_has_direct_pdf_download():
    script = (ROOT / "app/static/v820.js").read_text()
    css = (ROOT / "app/static/v820.css").read_text()
    index = (ROOT / "app/static/index.html").read_text()

    assert 'href="/api/bookings/${attr(r.id)}/final-timings.pdf" download' in script
    assert "↓ Download PDF" in script
    assert "v8331-answer-actions" in script
    assert ".v8331-answer-actions a" in css
    assert ".v8331-answer-actions a,.v8331-answer-actions button{width:100%" in css
    assert "/static/v820.css?v=final-timings-pdf-download-v8-33-1" in index
    assert "/static/v820.js?v=final-timings-pdf-download-v8-33-1" in index

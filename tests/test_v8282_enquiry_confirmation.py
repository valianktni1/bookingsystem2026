from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_static(name: str) -> str:
    return (ROOT / "app" / "static" / name).read_text(encoding="utf-8")


def test_success_confirmation_is_visible_and_accessible():
    html = read_static("enquiry.html")
    css = read_static("enquiry.css")

    assert 'id="success"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'tabindex="-1"' in html
    assert ".enquiry-complete .success" in css
    assert "position:fixed" in css
    assert "bottom:16px" in css


def test_submission_notifies_the_parent_and_focuses_confirmation():
    enquiry_js = read_static("enquiry.js")
    embed_js = read_static("enquiry-embed.js")

    assert 'type: "wbm-enquiry-submitted"' in enquiry_js
    assert 'type: "wbm-enquiry-height", height: 520' in enquiry_js
    assert "try { success.focus({preventScroll: true}); }" in enquiry_js
    assert "catch (_) { success.focus(); }" in enquiry_js
    assert '"wbm-enquiry-submitted"' in embed_js
    assert 'frame.scrollIntoView({behavior: "smooth", block: "center"})' in embed_js


def test_generated_embed_uses_cache_busted_confirmation_helper():
    app_js = read_static("app.js")
    builder_js = read_static("v897.js")
    expected = "/static/enquiry-embed.js?v=enquiry-confirmation-v8-28-2"

    assert expected in app_js
    assert expected in builder_js

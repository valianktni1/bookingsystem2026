from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_wedding_booking_form_has_durable_device_draft_recovery():
    js = source("app/static/client-v898.js")

    assert "const BOOKING_DRAFT_MAX_AGE = 30 * 24 * 60 * 60 * 1000" in js
    assert "wbm-booking-form-draft:" in js
    assert "localStorage.getItem(bookingDraftKey())" in js
    assert "localStorage.setItem(bookingDraftKey()" in js
    assert "localStorage.removeItem(bookingDraftKey())" in js
    assert "savedAt" in js
    assert "step: bookingStep" in js
    assert 'form.addEventListener("input", remember)' in js
    assert 'form.addEventListener("change", remember)' in js
    assert "{...existing(\"booking_form\"),...(savedDraft?.values||{})}" in js
    assert "Your saved answers have been restored" in js
    assert "Your answers are protected while you type" in js
    assert "if(type===\"booking_form\")clearBookingDraft()" in js
    assert "Your answers are still saved on this device" in js


def test_final_timings_has_durable_draft_and_migrates_old_session_draft():
    js = source("app/static/client-v820.js")

    assert "const TIMINGS_DRAFT_MAX_AGE = 30 * 24 * 60 * 60 * 1000" in js
    assert "wbm-final-timings-draft:" in js
    assert "localStorage.getItem(key)" in js
    assert "sessionStorage.getItem(key)" in js
    assert "localStorage.setItem(timingsDraftKey(),payload)" in js
    assert "sessionStorage.removeItem(key)" in js
    assert "localStorage.removeItem(timingsDraftKey())" in js
    assert "sessionStorage.removeItem(timingsDraftKey())" in js
    assert "step:timingsStep" in js
    assert "confirmed:Boolean" in js
    assert "Your saved timings have been restored" in js
    assert "Your timings are protected while you type" in js
    assert "clearTimingsDraft();data=await api" in js
    assert "Your answers are still saved on this device" in js


def test_draft_status_is_visible_and_versioned_assets_are_loaded():
    css = source("app/static/client-v820.css")
    html = source("app/static/client.html")

    assert ".client-draft-notice" in css
    assert "/static/client-v820.css?v=durable-form-drafts-v8-29" in html
    assert "/static/client-v898.js?v=durable-form-drafts-v8-29" in html
    assert "/static/client-v820.js?v=durable-form-drafts-v8-29" in html

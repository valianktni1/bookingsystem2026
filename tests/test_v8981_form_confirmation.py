from pathlib import Path

from app.booking_forms import default_booking_form


ROOT = Path(__file__).resolve().parents[1]


def test_booking_form_has_unambiguous_submit_wording():
    form = default_booking_form()
    assert form["submit_label"] == "Submit Wedding Booking Form"
    assert "wedding file" in form["success_message"]
    assert "available to Mark" in form["success_message"]


def test_client_uses_a_success_dialog_and_clear_next_step():
    script = (ROOT / "app/static/client-v898.js").read_text()
    stylesheet = (ROOT / "app/static/client-v898.css").read_text()
    assert 'role="dialog"' in script
    assert "It is safely in your wedding file" in script
    assert "Continue to agreement" in script
    assert "booking-submit-confirmation" in stylesheet

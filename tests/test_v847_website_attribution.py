import os
from pathlib import Path

from sqlalchemy import select


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v847.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v847-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v847-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.growth_integration import build_booking_payload
from app.main import ENQUIRY_HITS, app
from app.models import Booking


ATTRIBUTION = {
    "visit_id": "50c3f9da-bc2f-43fd-9f67-0fd5ca2cbe44",
    "source": "Google",
    "campaign": "12ab34cd56ef",
    "landing_path": "/real-weddings/hazel-gap/",
}


def reset_database():
    ENQUIRY_HITS.clear()
    engine.dispose()
    (TEST_ROOT / "test-v847.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v847.db-journal").unlink(missing_ok=True)


def enquiry(email="attribution@example.com", **changes):
    payload = {
        "primary_first_name": "Website",
        "partner_first_name": "Couple",
        "email": email,
        "phone": "07700 900555",
        "event_date": "2028-08-19",
        "location": "Hazel Gap Barn",
        "package_interest": "Gold",
        "selfie_booth_interest": "Maybe",
        "message": "Website attribution test",
        "heard_about_us": "Google search",
        "privacy_agreed": True,
        "custom_answers": {},
    }
    payload.update(changes)
    return payload


def test_consent_attribution_is_private_and_sent_to_growth():
    reset_database()
    with TestClient(app) as client:
        created = client.post("/api/public/enquiries", json=enquiry(website_attribution=ATTRIBUTION))
        assert created.status_code == 201, created.text
        with SessionLocal() as db:
            booking = db.scalar(select(Booking).where(Booking.title == "Website & Couple"))
            assert booking.workflow_state["growth_attribution"] == ATTRIBUTION
            assert "website_attribution" not in booking.form_data["website_enquiry"]
            growth_payload, _ = build_booking_payload(booking)
            assert growth_payload["website_attribution"] == ATTRIBUTION


def test_missing_attribution_still_works_and_bad_values_are_rejected():
    reset_database()
    with TestClient(app) as client:
        ordinary = client.post("/api/public/enquiries", json=enquiry("ordinary@example.com"))
        assert ordinary.status_code == 201
        bad = client.post("/api/public/enquiries", json=enquiry(
            "bad@example.com", event_date="2028-08-20",
            website_attribution={**ATTRIBUTION, "source": "Made up", "email": "hidden@example.com"},
        ))
        assert bad.status_code == 422


def test_iframe_messages_use_exact_origins_and_confirmed_success_only():
    root = Path(__file__).parents[1] / "app" / "static"
    form_js = (root / "enquiry.js").read_text()
    embed_js = (root / "enquiry-embed.js").read_text()
    assert '"https://perfectweddingsbymark.uk"' in form_js
    assert '"https://www.perfectweddingsbymark.uk"' in form_js
    assert 'postMessage(message, parentOrigin)' in form_js
    assert 'postMessage(message, "*")' not in form_js
    assert 'type: "wbm-enquiry-started"' in form_js
    assert 'window.wbmWebsiteEvent?.("enquiry_start")' in embed_js
    assert 'window.wbmWebsiteEvent?.("enquiry_success")' in embed_js
    assert embed_js.index('window.wbmWebsiteEvent?.("enquiry_success")') > embed_js.index('event.data.type === "wbm-enquiry-submitted"')


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v847.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v847.db-journal").unlink(missing_ok=True)

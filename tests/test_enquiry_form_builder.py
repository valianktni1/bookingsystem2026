import os
from pathlib import Path

TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'form-builder-test.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "form-builder-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"

from fastapi.testclient import TestClient

from app.database import engine
from app.main import ENQUIRY_HITS, app


def reset_database():
    ENQUIRY_HITS.clear()
    engine.dispose()
    (TEST_ROOT / "form-builder-test.db").unlink(missing_ok=True)
    (TEST_ROOT / "form-builder-test.db-journal").unlink(missing_ok=True)


def login(client: TestClient):
    response = client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    })
    assert response.status_code == 200


def enquiry_payload(**changes):
    payload = {
        "primary_first_name": "Taylor",
        "partner_first_name": "Jordan",
        "email": "taylor@example.com",
        "phone": "07123456789",
        "event_date": "2027-06-18",
        "location": "Peckforton Castle",
        "venue_address": "Stone House Lane, Tarporley",
        "package_interest": "Gold Package",
        "selfie_booth_interest": "Maybe - tell me more",
        "message": "We are planning an outdoor ceremony.",
        "promo_code": None,
        "heard_about_us": "Recommendation",
        "fun_answer": "Beans on toast",
        "privacy_agreed": True,
        "custom_answers": {},
    }
    payload.update(changes)
    return payload


def test_default_form_is_public_but_editor_requires_login():
    reset_database()
    with TestClient(app) as client:
        public = client.get("/api/public/enquiry-form")
        assert public.status_code == 200
        keys = [field["key"] for field in public.json()["fields"]]
        assert "location" in keys
        assert "privacy_agreed" in keys
        assert client.get("/api/forms/website-enquiry").status_code == 401
        editor = client.get("/static/v897.js")
        assert editor.status_code == 200
        assert "Save & publish" in editor.text
        assert "Custom question" in editor.text


def test_custom_question_is_published_validated_and_snapshotted():
    reset_database()
    with TestClient(app) as client:
        login(client)
        config = client.get("/api/forms/website-enquiry").json()
        config["fields"].insert(7, {
            "id": "custom_ceremony_style",
            "key": "custom_ceremony_style",
            "label": "What style of ceremony are you planning?",
            "field_type": "select",
            "placeholder": "Choose one",
            "help_text": "This helps Mark understand your day.",
            "required": True,
            "enabled": True,
            "width": "full",
            "options": ["Church", "Civil", "Outdoor"],
            "custom": True,
        })
        editable = {key: config[key] for key in (
            "heading", "introduction", "payment_title", "payment_options", "fields",
            "submit_label", "success_heading", "success_message",
        )}
        saved = client.put("/api/forms/website-enquiry", json=editable)
        assert saved.status_code == 200, saved.text
        assert any(field["key"] == "custom_ceremony_style"
                   for field in client.get("/api/public/enquiry-form").json()["fields"])

        missing = client.post("/api/public/enquiries", json=enquiry_payload())
        assert missing.status_code == 422
        assert "style of ceremony" in str(missing.json()["detail"])

        created = client.post("/api/public/enquiries", json=enquiry_payload(
            custom_answers={"custom_ceremony_style": "Outdoor"},
        ))
        assert created.status_code == 201, created.text
        rows = client.get("/api/bookings").json()
        booking_id = next(row["id"] for row in rows if row["client"]["email"] == "taylor@example.com")
        booking = client.get(f"/api/bookings/{booking_id}").json()
        enquiry = booking["form_data"]["website_enquiry"]
        assert enquiry["custom_answers"]["custom_ceremony_style"] == "Outdoor"
        snapshot = next(item for item in enquiry["answer_snapshot"]
                        if item["key"] == "custom_ceremony_style")
        assert snapshot["label"] == "What style of ceremony are you planning?"
        assert snapshot["answer"] == "Outdoor"


def test_essential_workflow_questions_cannot_be_removed_or_hidden():
    reset_database()
    with TestClient(app) as client:
        login(client)
        config = client.get("/api/forms/website-enquiry").json()
        editable = {key: config[key] for key in (
            "heading", "introduction", "payment_title", "payment_options", "fields",
            "submit_label", "success_heading", "success_message",
        )}
        editable["fields"] = [field for field in editable["fields"] if field["key"] != "email"]
        response = client.put("/api/forms/website-enquiry", json=editable)
        assert response.status_code == 422
        assert "Essential questions cannot be removed" in response.json()["detail"]

        config = client.get("/api/forms/website-enquiry").json()
        editable = {key: config[key] for key in (
            "heading", "introduction", "payment_title", "payment_options", "fields",
            "submit_label", "success_heading", "success_message",
        )}
        email = next(field for field in editable["fields"] if field["key"] == "email")
        email["enabled"] = False
        email["required"] = False
        saved = client.put("/api/forms/website-enquiry", json=editable)
        assert saved.status_code == 200
        protected_email = next(field for field in saved.json()["fields"] if field["key"] == "email")
        assert protected_email["enabled"] is True
        assert protected_email["required"] is True

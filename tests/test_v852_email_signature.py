import os
import shutil
from pathlib import Path

TEST_ROOT = Path(__file__).parent
DB_FILE = TEST_ROOT / "test-v852-email-signature.db"
STORAGE_ROOT = TEST_ROOT / "v852-email-signature-storage"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(STORAGE_ROOT)
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import engine
from app.email_service import build_email_message, email_signature_config
from app.main import app
from app.models import Booking, Brand, BusinessProfile, Client


ROOT = Path(__file__).parents[1]


def _booking() -> Booking:
    booking = Booking(brand=Brand.WBM, title="Sophie & James")
    booking.client = Client(first_name="Sophie", last_name="Taylor",
                            email="sophie@example.com")
    return booking


def _profile(**overrides) -> BusinessProfile:
    values = {
        "brand": Brand.WBM,
        "display_name": "Weddings By Mark",
        "invoice_prefix": "WBM",
        "email": "mark@perfectweddingsbymark.uk",
        "phone": "07712 117357",
        "website": "perfectweddingsbymark.uk",
    }
    values.update(overrides)
    return BusinessProfile(**values)


def test_weddings_by_mark_gets_the_requested_editable_signature_defaults():
    config = email_signature_config(_profile())
    assert config["text"] == (
        "Mark Powell\nWeddings By Mark\nMulti Award Winning Wedding Photographer\n"
        "07712 117357\nmark@perfectweddingsbymark.uk\nperfectweddingsbymark.uk"
    )
    assert config["show_logo"] is True
    assert config["show_awards"] is True


def test_signature_text_and_image_visibility_change_the_actual_email():
    profile = _profile(email_signature={
        "text": "All the best,\nMark\nWeddings By Mark",
        "show_logo": False,
        "show_awards": False,
    })
    message = build_email_message(
        _booking(), profile, "Hello", "Hi Sophie", "mark@perfectweddingsbymark.uk"
    )
    html = next(part.get_content() for part in message.walk()
                if part.get_content_type() == "text/html")
    images = [part for part in message.walk() if part.get_content_maintype() == "image"]
    assert "All the best,<br>Mark<br>Weddings By Mark" in html
    assert "cid:weddings-by-mark-logo" not in html
    assert "cid:weddings-by-mark-awards" not in html
    assert images == []


def test_custom_signature_image_is_embedded_from_backed_up_storage(tmp_path):
    settings = get_settings()
    original_root = settings.storage_root
    settings.storage_root = tmp_path
    try:
        custom = tmp_path / "business-email" / "wbm" / "logo-test.png"
        custom.parent.mkdir(parents=True)
        custom.write_bytes(b"\x89PNG\r\n\x1a\n" + b"safe-test-image")
        profile = _profile(email_signature={
            "text": "Mark\nWeddings By Mark",
            "show_logo": True,
            "show_awards": False,
            "logo_storage_name": "business-email/wbm/logo-test.png",
        })
        message = build_email_message(
            _booking(), profile, "Hello", "Hi Sophie", "mark@perfectweddingsbymark.uk"
        )
        images = [part for part in message.walk() if part.get_content_maintype() == "image"]
        assert [part.get_filename() for part in images] == ["logo-test.png"]
        assert images[0].get_payload(decode=True) == custom.read_bytes()
    finally:
        settings.storage_root = original_root


def test_business_settings_contains_mobile_friendly_signature_editor_and_safe_routes():
    javascript = (ROOT / "app" / "static" / "app.js").read_text()
    css = (ROOT / "app" / "static" / "app.css").read_text()
    main = (ROOT / "app" / "main.py").read_text()
    migrations = (ROOT / "app" / "migrations.py").read_text()
    assert "EMAIL SIGNATURE" in javascript
    assert "Signature wording" in javascript
    assert "Upload or replace" in javascript
    assert "maximum 3MB" in javascript
    assert "signature-assets{grid-template-columns:1fr}" in css
    assert "Upload a PNG or JPEG image" in main
    assert '"email_signature": "JSON NULL"' in migrations


def test_admin_can_save_upload_preview_and_remove_signature_artwork():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v852-email-signature.db-journal").unlink(missing_ok=True)
    shutil.rmtree(STORAGE_ROOT, ignore_errors=True)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        businesses = client.get("/api/businesses").json()
        wbm = next(row for row in businesses if row["brand"] == "wbm")
        assert "Mark Powell" in wbm["email_signature"]["text"]
        saved = client.patch("/api/businesses/wbm", json={
            "email_signature": {
                "text": "Mark Powell\nWeddings By Mark\nTelephone 07712 117357",
                "show_logo": True,
                "show_awards": True,
            },
        })
        assert saved.status_code == 200, saved.text
        assert next(row for row in saved.json() if row["brand"] == "wbm")["email_signature"]["text"].endswith("07712 117357")

        custom_png = b"\x89PNG\r\n\x1a\n" + b"email-signature-route-test"
        uploaded = client.post(
            "/api/businesses/wbm/email-signature/assets/logo",
            files={"file": ("new-logo.png", custom_png, "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text
        signature = next(row for row in uploaded.json() if row["brand"] == "wbm")["email_signature"]
        assert signature["has_custom_logo"] is True
        asset = client.get("/api/businesses/wbm/email-signature/assets/logo")
        assert asset.status_code == 200
        assert asset.content == custom_png
        assert asset.headers["content-type"].startswith("image/png")

        templates = client.get("/api/communications/templates?brand=wbm").json()["templates"]
        quote = next(row for row in templates if row["template_key"] == "quote")
        preview = client.get(f"/api/communications/templates/{quote['id']}/preview")
        assert preview.status_code == 200
        assert "Telephone 07712 117357" in preview.json()["html"]
        assert "/api/businesses/wbm/email-signature/assets/logo" in preview.json()["html"]

        removed = client.delete("/api/businesses/wbm/email-signature/assets/logo")
        assert removed.status_code == 200
        signature = next(row for row in removed.json() if row["brand"] == "wbm")["email_signature"]
        assert signature["has_custom_logo"] is False
        assert signature["show_logo"] is False

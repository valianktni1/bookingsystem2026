import os
from datetime import date
from decimal import Decimal
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v832.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v832-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v832-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, Brand, Client, Invoice, RecordKind, RecordStatus


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v832.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v832.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def test_wedding_list_exposes_package_and_outstanding_balance_for_friendly_cards():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            couple = Client(first_name="Friendly", last_name="Couple",
                            partner_name="Partner", email="friendly@example.com")
            db.add(couple)
            db.flush()
            booking = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING,
                status=RecordStatus.CONFIRMED, title="Friendly & Partner",
                client_id=couple.id, event_date=date(2027, 9, 18),
                venue_or_project="Readable Barn", package_name="Gold Package",
                quoted_total=Decimal("899.00"),
            )
            db.add(booking)
            db.flush()
            db.add(Invoice(
                booking_id=booking.id, brand=Brand.WBM, sequence=83201,
                number="WBM83201", total=Decimal("899.00"),
                paid=Decimal("200.00"), status="part_paid",
            ))
            db.commit()
            booking_id = booking.id

        row = next(item for item in client.get("/api/bookings").json()
                   if item["id"] == booking_id)
        assert row["package_name"] == "Gold Package"
        assert row["outstanding_total"] == 699.0


def test_mobile_workspace_has_large_direct_actions_and_no_horizontal_workflow():
    root = Path(__file__).parents[1]
    css = (root / "app/static/v832.css").read_text()
    js = (root / "app/static/v832.js").read_text()
    index = (root / "app/static/index.html").read_text()

    for label in ("Email", "Call", "Invoice", "Questionnaire", "Notes", "More"):
        assert f'"{label}"' in js
    assert 'selectRecordTab(record, "Payments", true)' in js
    assert 'selectRecordTab(record, "Forms", true)' in js
    assert 'selectRecordTab(record, "Notes", true)' in js
    assert ".record-stage-bar{display:none}" in css
    assert ".v832-quick-actions button{min-height:68px" in css
    assert ".v830-booking-open .client-cell strong{font-size:19px" in css
    assert ".v8301-mobile-section>button strong{font-size:18px" in css
    assert "/static/v832.css?v=final-timings-shortcut-v8-33" in index
    assert "/static/v832.js?v=final-timings-shortcut-v8-33" in index
    assert index.index("v8301.js") < index.index("v832.js")
    assert "BOOKINGSYSTEM2026 · COMPLETE V8.36.1" in index


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v832.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v832.db-journal").unlink(missing_ok=True)

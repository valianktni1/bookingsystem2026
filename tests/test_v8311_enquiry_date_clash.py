import os
from datetime import date, datetime, timezone
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v8311.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v8311-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v8311-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, Brand, Client, RecordKind, RecordStatus


CLASH_DATE = date(2027, 8, 14)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v8311.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v8311.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def add_wedding(db, title, status, *, archived=False, is_test=False):
    client = Client(first_name=title, last_name="Couple",
                    email=f"{title.lower().replace(' ', '-')}@example.com")
    db.add(client)
    db.flush()
    booking = Booking(
        brand=Brand.WBM,
        kind=RecordKind.WEDDING,
        status=status,
        title=title,
        client_id=client.id,
        event_date=CLASH_DATE,
        venue_or_project="Clash Test Venue",
        is_test=is_test,
        archived_at=datetime.now(timezone.utc) if archived else None,
    )
    db.add(booking)
    db.flush()
    return booking


def test_new_enquiry_is_warned_when_the_date_already_has_a_wedding():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            booked = add_wedding(db, "Already Booked", RecordStatus.CONFIRMED)
            enquiry = add_wedding(db, "Yesterday Enquiry", RecordStatus.ENQUIRY)
            db.commit()
            booked_id, enquiry_id = booked.id, enquiry.id

        rows = {row["id"]: row for row in client.get("/api/bookings").json()}
        enquiry_conflict = rows[enquiry_id]["same_date_conflict"]
        assert enquiry_conflict == {
            "has_conflict": True,
            "booked_weddings": 1,
            "open_enquiries": 1,
            "other_booked_weddings": 1,
            "other_open_enquiries": 0,
            "total_records": 2,
        }
        booked_conflict = rows[booked_id]["same_date_conflict"]
        assert booked_conflict["has_conflict"] is True
        assert booked_conflict["other_booked_weddings"] == 0
        assert booked_conflict["other_open_enquiries"] == 1

        opened = client.get(f"/api/bookings/{enquiry_id}").json()
        assert opened["same_date_conflict"] == enquiry_conflict


def test_archived_booked_wedding_still_warns_a_live_enquiry_but_noise_is_excluded():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            add_wedding(db, "Archived Booked Date", RecordStatus.IN_PROGRESS, archived=True)
            live = add_wedding(db, "Live Enquiry", RecordStatus.QUOTED)
            add_wedding(db, "Archived Enquiry", RecordStatus.ENQUIRY, archived=True)
            add_wedding(db, "Cancelled", RecordStatus.CANCELLED)
            add_wedding(db, "Testing", RecordStatus.CONFIRMED, is_test=True)
            db.commit()
            live_id = live.id

        live_row = next(row for row in client.get("/api/bookings").json()
                        if row["id"] == live_id)
        assert live_row["same_date_conflict"]["booked_weddings"] == 1
        assert live_row["same_date_conflict"]["open_enquiries"] == 1
        assert live_row["same_date_conflict"]["other_booked_weddings"] == 1
        assert live_row["same_date_conflict"]["has_conflict"] is True


def test_date_clash_and_expired_session_messages_are_prominent_and_private():
    root = Path(__file__).parents[1]
    admin_js = (root / "app/static/app.js").read_text()
    client_js = (root / "app/static/client.js").read_text()
    css = (root / "app/static/app.css").read_text()

    assert "DATE CLASH WARNING" in admin_js
    assert "DATE BOOKED" in admin_js
    assert "sameDateConflictBanner" in admin_js
    assert ".same-date-conflict-banner" in css
    assert "Your booking-system session expired" in admin_js
    assert "Nothing was sent" in admin_js
    assert "same_date_conflict" not in client_js


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v8311.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v8311.db-journal").unlink(missing_ok=True)

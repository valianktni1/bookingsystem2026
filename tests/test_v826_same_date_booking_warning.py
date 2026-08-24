import os
from datetime import date
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v826.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v826-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v826-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, Brand, Client, RecordKind, RecordStatus


CLASH_DATE = date(2027, 6, 12)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v826.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v826.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def add_record(db, title, status, *, brand=Brand.WBM, kind=RecordKind.WEDDING,
               is_test=False):
    email = title.lower().replace(" ", "-").replace("&", "and") + "@example.com"
    client = Client(first_name=title, last_name="Couple", email=email)
    db.add(client)
    db.flush()
    booking = Booking(
        brand=brand,
        kind=kind,
        status=status,
        title=title,
        client_id=client.id,
        event_date=CLASH_DATE,
        venue_or_project="Test Venue",
        is_test=is_test,
    )
    db.add(booking)
    db.flush()
    return booking


def test_only_active_real_wbm_weddings_create_the_same_date_warning():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            first = add_record(db, "Alpha Wedding", RecordStatus.CONFIRMED)
            second = add_record(db, "Beta Wedding", RecordStatus.IN_PROGRESS)
            add_record(db, "Date Enquiry", RecordStatus.ENQUIRY)
            add_record(db, "Cancelled Wedding", RecordStatus.CANCELLED)
            add_record(db, "Testing Wedding", RecordStatus.CONFIRMED, is_test=True)
            add_record(
                db, "Ivory Project", RecordStatus.CONFIRMED,
                brand=Brand.IVORY, kind=RecordKind.DIGITAL,
            )
            db.commit()
            second_id = second.id

        rows = client.get("/api/bookings").json()
        counts = {row["title"]: row["same_date_active_booking_count"] for row in rows}
        assert counts["Alpha Wedding"] == 2
        assert counts["Beta Wedding"] == 2
        assert counts["Date Enquiry"] == 0
        assert counts["Cancelled Wedding"] == 0
        assert counts["Testing Wedding"] == 0
        assert counts["Ivory Project"] == 0

        # Searching for only one member of the pair must retain the warning.
        searched = client.get("/api/bookings?q=Alpha").json()
        assert [(row["title"], row["same_date_active_booking_count"]) for row in searched] == [
            ("Alpha Wedding", 2),
        ]

        # Once one genuine booking is cancelled, the remaining wedding is no
        # longer falsely presented as a date clash.
        with SessionLocal() as db:
            db.get(Booking, second_id).status = RecordStatus.CANCELLED
            db.commit()
        refreshed = client.get("/api/bookings?q=Alpha").json()
        assert refreshed[0]["same_date_active_booking_count"] == 1


def test_private_warning_is_wired_only_into_the_admin_booking_list():
    root = Path(__file__).parents[1]
    admin_js = (root / "app/static/app.js").read_text()
    client_js = (root / "app/static/client.js").read_text()
    css = (root / "app/static/app.css").read_text()
    index = (root / "app/static/index.html").read_text()

    assert "sameDateBookingWarning" in admin_js
    assert "same_date_active_booking_count" in admin_js
    assert "Caution:" in admin_js
    assert "same-date-booking-warning" in admin_js
    assert ".same-date-booking-warning" in css
    assert "sameDateBookingWarning" not in client_js
    assert "same_date_active_booking_count" not in client_js
    assert "/static/app.css?v=same-date-booking-warning-v8-26" in index
    assert "/static/app.js?v=enquiry-embed-hotfix-v8-28-1" in index


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v826.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v826.db-journal").unlink(missing_ok=True)

import os
from datetime import date, datetime, timezone
from pathlib import Path

TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"
os.environ["INVOICE_START"] = "2000"

from fastapi.testclient import TestClient

from app.database import SessionLocal, engine
from app.main import app
from app.models import (Booking, Brand, Client, Invoice, Payment, Quote,
                        RecordKind, RecordStatus)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)


def add_wedding(db, suffix: str, wedding_date: date, status: RecordStatus, **kwargs) -> Booking:
    client = Client(
        id=f"client-availability-{suffix}",
        first_name="Private",
        last_name="Couple",
        email=f"availability-{suffix}@example.com",
    )
    booking = Booking(
        id=f"booking-availability-{suffix}",
        brand=Brand.WBM,
        kind=RecordKind.WEDDING,
        title=f"Private Couple {suffix}",
        client_id=client.id,
        event_date=wedding_date,
        status=status,
        **kwargs,
    )
    db.add_all([client, booking])
    db.flush()
    return booking


def secure_native_wedding(db, booking: Booking, sequence: int) -> None:
    invoice = Invoice(
        booking_id=booking.id, brand=Brand.WBM, sequence=sequence,
        number=f"WBM{sequence:05d}", issue_date=date.today(),
        total=100, paid=100, status="paid",
    )
    db.add(invoice)
    db.flush()
    db.add(Payment(
        invoice_id=invoice.id, amount=100, paid_date=date.today(),
        payment_type="bank_transfer",
    ))


def test_live_availability_returns_only_privacy_safe_date_statuses():
    reset_database()
    open_date = date(2030, 6, 1)
    blocked_date = date(2030, 6, 2)
    accepted_date = date(2030, 6, 3)
    archived_date = date(2030, 6, 4)

    with TestClient(app) as client:
        response = client.get(f"/api/public/availability?date={open_date.isoformat()}")
        assert response.status_code == 200
        assert response.text == "Available"
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["cache-control"] == "no-store, max-age=0"

        with SessionLocal() as db:
            # These must never block a public date.
            add_wedding(db, "enquiry", open_date, RecordStatus.ENQUIRY)
            add_wedding(db, "cancelled", open_date, RecordStatus.CANCELLED)
            add_wedding(db, "test", open_date, RecordStatus.CONFIRMED, is_test=True)

            # Imported confirmed weddings are still genuine diary commitments.
            add_wedding(
                db,
                "legacy",
                blocked_date,
                RecordStatus.CONFIRMED,
                legacy_source="studio_ninja",
                legacy_id="legacy-availability-blocker",
            )

            accepted = add_wedding(db, "accepted", accepted_date, RecordStatus.QUOTED)
            db.add(Quote(
                id="quote-availability-accepted",
                booking_id=accepted.id,
                status="accepted",
                accepted_at=datetime.now(timezone.utc),
            ))

            archived = add_wedding(
                db,
                "archived",
                archived_date,
                RecordStatus.IN_PROGRESS,
                archived_at=datetime.now(timezone.utc),
            )
            secure_native_wedding(db, archived, 9801)
            db.commit()

        assert client.get(f"/api/public/availability?date={open_date.isoformat()}").text == "Available"
        assert client.get(f"/api/public/availability?date={blocked_date.isoformat()}").text == "Booked"
        assert client.get(f"/api/public/availability?date={accepted_date.isoformat()}").text == "Available"
        assert client.get(f"/api/public/availability?date={archived_date.isoformat()}").text == "Booked"
        assert client.get("/api/public/availability?date=2020-01-01").text == "Unavailable"

        # The public response must never reveal any name, venue or booking ID.
        for checked in (blocked_date, accepted_date, archived_date):
            body = client.get(f"/api/public/availability?date={checked.isoformat()}").text
            assert body in {"Booked", "Available", "Unavailable"}
            assert "Private" not in body


def test_live_availability_rejects_invalid_dates():
    reset_database()
    with TestClient(app) as client:
        assert client.get("/api/public/availability?date=not-a-date").status_code == 422

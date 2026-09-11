import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v8471.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v8471-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v8471-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient

from app import growth_integration
from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, Brand, Client, RecordKind, RecordStatus


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v8471.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v8471.db-journal").unlink(missing_ok=True)


def add_booking(db, *, month, amount, status=RecordStatus.CONFIRMED,
                deposit=False, test=False, archived=False, brand=Brand.WBM,
                kind=RecordKind.WEDDING):
    client = Client(first_name="Planning", last_name="Test", email=f"planning-{month}-{amount}@example.com")
    db.add(client)
    db.flush()
    db.add(Booking(
        brand=brand,
        kind=kind,
        status=status,
        title=f"Planning {month} {amount}",
        client_id=client.id,
        event_date=date(2027, month, 10),
        quoted_total=Decimal(str(amount)),
        deposit_paid_date=date(2026, 9, 1) if deposit else None,
        is_test=test,
        archived_at=datetime.now(timezone.utc) if archived else None,
    ))


def test_private_year_totals_include_only_real_won_weddings(monkeypatch):
    reset_database()
    key = "planning-private-test-key"
    monkeypatch.setattr(growth_integration.settings, "growth_integration_enabled", True)
    monkeypatch.setattr(growth_integration.settings, "growth_integration_key", key)
    with TestClient(app) as client:
        with SessionLocal() as db:
            add_booking(db, month=1, amount=699)
            add_booking(db, month=2, amount=475, status=RecordStatus.QUOTED, deposit=True)
            add_booking(db, month=3, amount=899, status=RecordStatus.ENQUIRY)
            add_booking(db, month=4, amount=1350, status=RecordStatus.CANCELLED, deposit=True)
            add_booking(db, month=5, amount=1799, test=True)
            add_booking(db, month=6, amount=899, archived=True)
            add_booking(db, month=7, amount=399, brand=Brand.IVORY, kind=RecordKind.DIGITAL)
            db.commit()
        url = "/api/integrations/growth/planning?year=2027"
        assert client.get(url).status_code == 401
        response = client.get(url, headers={"X-Integration-Key": key})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["bookings"] == 2
        assert Decimal(data["booked_value"]) == Decimal("1174.00")
        assert data["months"][0]["bookings"] == 1
        assert Decimal(data["months"][0]["booked_value"]) == Decimal("699.00")
        assert data["months"][1]["bookings"] == 1
        assert data["scope"] == "All real Booking weddings"
        assert client.get("/api/integrations/growth/planning?year=1900",
                          headers={"X-Integration-Key": key}).status_code == 422


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v8471.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v8471.db-journal").unlink(missing_ok=True)

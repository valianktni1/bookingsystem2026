import os
from datetime import date
from decimal import Decimal
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
from app.google_calendar import (calendar_event_payload, decrypt_refresh_token,
                                 encrypt_refresh_token, sync_booking_calendar_safely)
from app.main import app
from app.models import Booking, Brand, Client, Quote, RecordKind, RecordStatus


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)


def test_calendar_event_contains_couple_first_venue_and_ceremony_without_attendees():
    booking = Booking(
        id="booking-calendar-payload", brand=Brand.WBM, kind=RecordKind.WEDDING,
        status=RecordStatus.QUOTED, title="Sophie & James", client_id="client-calendar-payload",
        event_date=date(2027, 6, 12), venue_or_project="Peckforton Castle",
        venue_address="Peckforton Castle, Tarporley", package_name="Platinum",
        form_data={"ceremony_time": "13:30", "ceremony_details": "Peckforton Castle Chapel"},
    )
    payload = calendar_event_payload(booking)
    assert payload["summary"] == "Wedding — Sophie & James — Peckforton Castle — Ceremony 13:30"
    assert "Couple: Sophie & James" in payload["description"]
    assert "First/main venue: Peckforton Castle" in payload["description"]
    assert "Ceremony time: 13:30" in payload["description"]
    assert payload["location"] == "Peckforton Castle, Tarporley"
    assert payload["start"] == {"date": "2027-06-12"}
    assert payload["end"] == {"date": "2027-06-13"}
    assert payload["id"].startswith("b")
    assert len(payload["id"]) == 41
    assert "attendees" not in payload


def test_refresh_token_is_encrypted_at_rest():
    encrypted = encrypt_refresh_token("test-google-refresh-token")
    assert encrypted != "test-google-refresh-token"
    assert "test-google-refresh-token" not in encrypted
    assert decrypt_refresh_token(encrypted) == "test-google-refresh-token"


def test_one_google_event_is_created_updated_then_removed_while_booking_remains(monkeypatch):
    reset_database()
    calls = []

    def fake_request(method, path, token, *, json=None):
        calls.append((method, path, json))
        if method == "DELETE":
            return FakeResponse(204)
        return FakeResponse(200, {"id": "google-event-123", "htmlLink": "https://calendar.google.com/event/123"})

    monkeypatch.setattr("app.google_calendar.google_calendar_configured", lambda: True)
    monkeypatch.setattr("app.google_calendar._connection", lambda db: {
        "encrypted_refresh_token": "not-used", "calendar_id": "primary"
    })
    monkeypatch.setattr("app.google_calendar._access_token", lambda connection: "access-token")
    monkeypatch.setattr("app.google_calendar._calendar_request", fake_request)

    with TestClient(app):
        with SessionLocal() as db:
            client = Client(first_name="Sophie", last_name="Taylor", partner_name="James",
                            email="sophie@example.com")
            db.add(client)
            db.flush()
            booking = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.QUOTED,
                title="Sophie & James", client_id=client.id, event_date=date(2027, 6, 12),
                venue_or_project="Peckforton Castle", venue_address="Tarporley",
                package_name="Platinum", quoted_total=Decimal("1299"),
                form_data={"ceremony_time": "13:00"},
            )
            db.add(booking)
            db.flush()
            db.add(Quote(booking_id=booking.id, status="accepted", total=Decimal("1299")))
            db.commit()

            created = sync_booking_calendar_safely(db, booking)
            assert created["status"] == "synced"
            assert created["event_id"] == "google-event-123"
            assert calls[-1][0] == "POST"
            assert calls[-1][2]["summary"].endswith("Ceremony 13:00")

            booking.form_data = {"ceremony_time": "14:15"}
            db.commit()
            updated = sync_booking_calendar_safely(db, booking)
            assert updated["event_id"] == "google-event-123"
            assert calls[-1][0] == "PUT"
            assert calls[-1][2]["summary"].endswith("Ceremony 14:15")

            booking.status = RecordStatus.CANCELLED
            db.commit()
            removed = sync_booking_calendar_safely(db, booking)
            assert removed["status"] == "removed"
            assert removed["removed_event_id"] == "google-event-123"
            assert calls[-1][0] == "DELETE"

            retained = db.get(Booking, booking.id)
            assert retained is not None
            assert retained.status == RecordStatus.CANCELLED
            assert retained.workflow_state["google_calendar"]["status"] == "removed"


def test_settings_explain_calendar_setup_without_exposing_a_secret():
    reset_database()
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        status = client.get("/api/integrations/google-calendar/status")
        assert status.status_code == 200
        assert status.json()["connected"] is False
        assert status.json()["calendar"] == "Primary Google Calendar"
        assert "client_secret" not in str(status.json()).lower()

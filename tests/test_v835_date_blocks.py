import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v835.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v835-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v835-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient

import app.google_calendar as calendar_module
from app.backup import _readable_registers
from app.database import SessionLocal, engine
from app.main import app
from app.models import (Booking, Brand, Client, DateBlock, EmailLog, Invoice,
                        RecordKind, RecordStatus)


BLOCK_START = date.today() + timedelta(days=120)
BLOCK_END = BLOCK_START + timedelta(days=13)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v835.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v835.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def add_enquiry(db, wedding_date=BLOCK_START):
    person = Client(first_name="Blocked", last_name="Enquiry", email="blocked@example.com")
    db.add(person)
    db.flush()
    booking = Booking(
        brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.ENQUIRY,
        title="Blocked Date Couple", client_id=person.id,
        event_date=wedding_date, venue_or_project="Test Venue",
    )
    db.add(booking)
    db.flush()
    return booking


def test_admin_can_block_range_and_public_checker_only_says_booked():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            before = {
                "clients": len(db.query(Client).all()),
                "invoices": len(db.query(Invoice).all()),
                "emails": len(db.query(EmailLog).all()),
            }

        response = client.post("/api/date-blocks", json={
            "start_date": BLOCK_START.isoformat(),
            "end_date": BLOCK_END.isoformat(),
            "label": "Private family holiday",
            "notes": "This must never appear on the public checker",
        })
        assert response.status_code == 201, response.text
        block = response.json()
        assert block["calendar_status"] == "pending"
        assert block["label"] == "Private family holiday"

        first = client.get("/api/public/availability", params={"date": BLOCK_START.isoformat()})
        middle = client.get("/api/public/availability", params={
            "date": (BLOCK_START + timedelta(days=7)).isoformat(),
        })
        last = client.get("/api/public/availability", params={"date": BLOCK_END.isoformat()})
        after = client.get("/api/public/availability", params={
            "date": (BLOCK_END + timedelta(days=1)).isoformat(),
        })
        assert (first.text, middle.text, last.text, after.text) == (
            "Booked", "Booked", "Booked", "Available",
        )
        assert "holiday" not in first.text.lower()
        assert "family" not in first.text.lower()

        with SessionLocal() as db:
            after_counts = {
                "clients": len(db.query(Client).all()),
                "invoices": len(db.query(Invoice).all()),
                "emails": len(db.query(EmailLog).all()),
            }
            assert after_counts == before
            registers = _readable_registers(db)
            assert "registers/date-blocks.csv" in registers
            assert b"Private family holiday" in registers["registers/date-blocks.csv"]


def test_block_warns_enquiry_and_requires_confirmation_for_existing_records():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            enquiry = add_enquiry(db)
            db.commit()
            enquiry_id = enquiry.id

        payload = {
            "start_date": BLOCK_START.isoformat(),
            "end_date": BLOCK_END.isoformat(),
            "label": "Holiday",
        }
        refused = client.post("/api/date-blocks", json=payload)
        assert refused.status_code == 409
        assert "existing wedding or enquiry" in refused.json()["detail"]

        payload["confirm_conflicts"] = True
        accepted = client.post("/api/date-blocks", json=payload)
        assert accepted.status_code == 201, accepted.text

        record = client.get(f"/api/bookings/{enquiry_id}").json()
        conflict = record["same_date_conflict"]
        assert conflict["has_conflict"] is True
        assert conflict["blocked_dates"] == 1
        assert conflict["is_manually_blocked"] is True
        assert conflict["other_booked_weddings"] == 0
        assert conflict["other_open_enquiries"] == 0


def test_edit_and_remove_update_website_without_deleting_audit_tombstone():
    reset_database()
    with TestClient(app) as client:
        login(client)
        created = client.post("/api/date-blocks", json={
            "start_date": BLOCK_START.isoformat(), "end_date": BLOCK_END.isoformat(),
            "label": "Holiday", "notes": None,
        }).json()
        moved_start = BLOCK_START + timedelta(days=1)
        moved_end = BLOCK_END + timedelta(days=2)
        updated = client.put(f"/api/date-blocks/{created['id']}", json={
            "start_date": moved_start.isoformat(), "end_date": moved_end.isoformat(),
            "label": "Annual leave", "notes": "Updated privately",
        })
        assert updated.status_code == 200, updated.text
        assert updated.json()["label"] == "Annual leave"
        assert client.get("/api/public/availability", params={
            "date": BLOCK_START.isoformat(),
        }).text == "Available"
        assert client.get("/api/public/availability", params={
            "date": moved_end.isoformat(),
        }).text == "Booked"

        removed = client.delete(f"/api/date-blocks/{created['id']}")
        assert removed.status_code == 200
        assert "No client email" in removed.json()["message"]
        assert client.get("/api/public/availability", params={
            "date": moved_start.isoformat(),
        }).text == "Available"
        assert client.get("/api/date-blocks").json() == []
        with SessionLocal() as db:
            retained = db.get(DateBlock, created["id"])
            assert retained is not None
            assert retained.deleted_at is not None


def test_google_calendar_block_is_one_inclusive_all_day_event_and_syncs_changes(monkeypatch):
    reset_database()
    calls = []
    monkeypatch.setattr(calendar_module, "google_calendar_configured", lambda: True)
    monkeypatch.setattr(calendar_module, "_connection", lambda db: {
        "encrypted_refresh_token": "not-used", "calendar_id": "primary",
    })
    monkeypatch.setattr(calendar_module, "_access_token", lambda connection: "token")

    class Response:
        status_code = 200

        def __init__(self, event_id="block-event"):
            self.event_id = event_id

        def json(self):
            return {"id": self.event_id, "htmlLink": "https://calendar.google.test/event"}

    def request(method, path, token, *, json=None):
        calls.append((method, path, json))
        if method == "DELETE":
            response = Response()
            response.status_code = 204
            return response
        return Response()

    monkeypatch.setattr(calendar_module, "_calendar_request", request)
    with TestClient(app):
        with SessionLocal() as db:
            block = DateBlock(
                start_date=BLOCK_START, end_date=BLOCK_END,
                label="Holiday", notes="Private notes",
            )
            db.add(block)
            db.commit()
            block_id = block.id

            created = calendar_module.sync_date_block_calendar_safely(db, block)
            assert created["status"] == "synced"
            assert calls[-1][0] == "POST"
            payload = calls[-1][2]
            assert payload["start"]["date"] == BLOCK_START.isoformat()
            assert payload["end"]["date"] == (BLOCK_END + timedelta(days=1)).isoformat()
            assert payload["summary"] == "Unavailable — Holiday"

            block.label = "Family time"
            db.commit()
            updated = calendar_module.sync_date_block_calendar_safely(db, block)
            assert updated["status"] == "synced"
            assert calls[-1][0] == "PUT"
            assert calls[-1][2]["summary"] == "Unavailable — Family time"

            block.deleted_at = calendar_module.datetime.now(calendar_module.timezone.utc)
            db.commit()
            removed = calendar_module.sync_date_block_calendar_safely(db, block)
            assert removed["status"] == "removed"
            assert calls[-1][0] == "DELETE"
            assert db.get(DateBlock, block_id).google_calendar_state["status"] == "removed"


def test_frontend_and_build_expose_clear_mobile_date_block_controls():
    root = Path(__file__).parents[1]
    js = (root / "app/static/v835.js").read_text()
    css = (root / "app/static/v835.css").read_text()
    index = (root / "app/static/index.html").read_text()
    assert "Block dates / holiday" in js
    assert "DATE BLOCKED" in js
    assert "No client emails or invoices" in js
    assert "Google Calendar synced" in js
    assert "@media(max-width:700px)" in css
    assert "/static/v835.js?v=manual-date-blocks-v8-35" in index
    assert "/static/v835.css?v=manual-date-blocks-v8-35" in index
    assert "MANUAL DATE BLOCKS V8.35" in index


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v835.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v835.db-journal").unlink(missing_ok=True)

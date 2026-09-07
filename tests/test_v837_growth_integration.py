import os
from pathlib import Path
from uuid import uuid4

TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"

from fastapi.testclient import TestClient

from app import growth_integration
from app.database import SessionLocal
from app.main import app
from app.models import Booking, GrowthLeadLink


def test_secure_manual_growth_enquiry_is_idempotent_and_sends_no_email(monkeypatch):
    key = "test-growth-key-that-is-at-least-thirty-two-characters-long"
    monkeypatch.setattr(growth_integration.settings, "growth_integration_key", key)
    monkeypatch.setattr(growth_integration.settings, "growth_integration_enabled", True)
    lead_id = f"growth-{uuid4()}"
    payload = {
        "event_id": f"growth-enquiry:{lead_id}",
        "growth_lead_id": lead_id,
        "primary_first_name": "Test",
        "partner_first_name": "Couple",
        "email": "test-couple@example.com",
        "event_date": "2028-09-12",
        "venue": "Test Venue",
        "package_interest": "Gold",
        "referral_source": "Telephone",
        "message": "Connector test",
        "is_test": True,
    }
    with TestClient(app) as client:
        rejected = client.post("/api/integrations/growth/enquiry", json=payload)
        assert rejected.status_code == 401
        headers = {"X-Integration-Key": key}
        created = client.post("/api/integrations/growth/enquiry", headers=headers, json=payload)
        assert created.status_code == 201
        assert created.json()["emails_sent"] == 0
        repeated = client.post("/api/integrations/growth/enquiry", headers=headers, json=payload)
        assert repeated.status_code == 201
        assert repeated.json()["already_processed"] is True

    with SessionLocal() as db:
        link = db.get(GrowthLeadLink, lead_id)
        assert link is not None
        booking = db.get(Booking, link.booking_id)
        assert booking.workflow_state["source"] == "growth_engine"
        assert booking.is_test is True


def test_booking_snapshot_event_id_changes_only_when_booking_changes():
    with SessionLocal() as db:
        booking = db.query(Booking).filter(Booking.is_test.is_(True)).order_by(Booking.created_at.desc()).first()
        first, first_hash = growth_integration.build_booking_payload(booking)
        second, second_hash = growth_integration.build_booking_payload(booking)
        assert first["event_id"] == second["event_id"]
        assert first_hash == second_hash
        booking.package_name = "Platinum"
        changed, changed_hash = growth_integration.build_booking_payload(booking)
        assert changed["event_id"] != first["event_id"]
        assert changed_hash != first_hash

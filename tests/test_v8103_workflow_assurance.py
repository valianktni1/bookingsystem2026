import os
from datetime import date, timedelta
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
from sqlalchemy import delete, select

from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, ContractAcceptance, EmailLog


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def booking_payload(title="New System Couple"):
    return {
        "brand": "wbm", "kind": "wedding", "status": "confirmed", "title": title,
        "client": {"first_name": "Alex", "last_name": "Test", "partner_name": "Sam",
                   "email": "couple@example.com", "phone": "07700 900111"},
        "event_date": (date.today() + timedelta(days=240)).isoformat(),
        "venue_or_project": "Test Hall", "venue_address": "Test Hall, Manchester",
        "package_name": "Gold", "quoted_total": 899, "deposit_amount": 100,
    }


def test_future_client_acceptance_is_countersigned_emailed_and_viewable(monkeypatch):
    reset_database()
    sent = []

    def fake_send(db, booking, profile, template, portal_url=None, **kwargs):
        sent.append((booking.id, template.template_key, portal_url))
        return template.subject, template.body

    monkeypatch.setattr("app.main.smtp_ready", lambda brand=None: True)
    monkeypatch.setattr("app.main.send_booking_template_email", fake_send)

    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json=booking_payload()).json()
        portal = client.post(f"/api/bookings/{booking['id']}/portal", json={"expires_days": 365}).json()
        token = portal["url"].split("/client/")[1]

        accepted = client.post(f"/api/client/{token}/contract", json={
            "accepted_name": "Alex Test", "accepted_email": "couple@example.com", "agreed": True,
        })
        assert accepted.status_code == 200
        assert accepted.json()["supplier_signed_name"] == "Mark Adam Powell"
        assert accepted.json()["supplier_signed_at"]
        assert accepted.json()["completion_email_sent"] is True
        assert sent and sent[0][1] == "contract_completed"
        assert sent[0][2].endswith("?tab=agreement")

        status = client.get(f"/api/client/{token}").json()
        assert status["contract"]["fully_signed"] is True
        assert status["contract"]["supplier_signed_name"] == "Mark Adam Powell"
        assert status["contract"]["supplier_signature_method"] == "automatic_after_client_acceptance"

        admin_pdf = client.get(f"/api/bookings/{booking['id']}/contract.pdf?inline=true")
        assert admin_pdf.status_code == 200
        assert admin_pdf.content.startswith(b"%PDF")
        assert admin_pdf.headers["content-disposition"].startswith("inline")
        public_pdf = client.get(f"/api/client/{token}/contract.pdf")
        assert public_pdf.status_code == 200
        assert public_pdf.content.startswith(b"%PDF")
        assert public_pdf.headers["content-disposition"].startswith("attachment")

        resent = client.post(f"/api/bookings/{booking['id']}/contract/completion-email")
        assert resent.status_code == 200
        assert resent.json()["completion_email_sent"] is True
        assert [item[1] for item in sent] == ["contract_completed", "contract_completed"]


def test_one_time_countersign_for_existing_native_acceptance_and_legacy_protection(monkeypatch):
    reset_database()
    sent = []

    def fake_send(db, booking, profile, template, portal_url=None, **kwargs):
        sent.append(booking.id)
        return template.subject, template.body

    monkeypatch.setattr("app.main.smtp_ready", lambda brand=None: True)
    monkeypatch.setattr("app.main.send_booking_template_email", fake_send)

    with TestClient(app) as client:
        login(client)
        native = client.post("/api/bookings", json=booking_payload("Today's Couple")).json()
        portal = client.post(f"/api/bookings/{native['id']}/portal", json={"expires_days": 365}).json()
        token = portal["url"].split("/client/")[1]
        assert client.post(f"/api/client/{token}/contract", json={
            "accepted_name": "Alex Test", "accepted_email": "couple@example.com", "agreed": True,
        }).status_code == 200

        # Recreate the exact state of a client acceptance made immediately before this update.
        with SessionLocal() as db:
            acceptance = db.scalar(select(ContractAcceptance).where(
                ContractAcceptance.booking_id == native["id"]
            ))
            acceptance.supplier_signed_name = None
            acceptance.supplier_signed_at = None
            acceptance.supplier_signature_method = None
            db.execute(delete(EmailLog).where(
                EmailLog.booking_id == native["id"],
                EmailLog.template_key == "contract_completed",
            ))
            db.commit()
        sent.clear()

        countersigned = client.post(f"/api/bookings/{native['id']}/contract/countersign")
        assert countersigned.status_code == 200
        assert countersigned.json()["contract"]["fully_signed"] is True
        assert countersigned.json()["contract"]["supplier_signed_name"] == "Mark Adam Powell"
        assert countersigned.json()["completion_email_sent"] is True
        assert sent == [native["id"]]
        assert client.post(f"/api/bookings/{native['id']}/contract/countersign").status_code == 409

        legacy = client.post("/api/bookings", json=booking_payload("Imported Couple")).json()
        with SessionLocal() as db:
            booking = db.get(Booking, legacy["id"])
            booking.legacy_source = "studio_ninja"
            db.add(ContractAcceptance(
                booking_id=booking.id, contract_title="Original contract", contract_version="legacy",
                contract_body="Original retained wording", accepted_name="Imported Client",
                accepted_email="couple@example.com", acceptance_source="studio_ninja_import",
                source_detail="Original retained document", is_legacy_import=True,
            ))
            db.commit()
        assert client.post(f"/api/bookings/{legacy['id']}/contract/countersign").status_code == 409
        assert sent == [native["id"]]

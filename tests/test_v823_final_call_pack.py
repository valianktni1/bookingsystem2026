import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v823.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v823-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v823-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.final_call_pack import CHECKLIST_ITEMS
from app.main import app
from app.models import (Booking, Brand, Client, ContractAcceptance, Document, EmailLog,
                        FormSubmission, Invoice, RecordKind, RecordStatus, ReminderLog, Task)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v823.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v823.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def add_wedding(db, *, imported=False):
    couple = Client(
        first_name="Sophie", last_name="Taylor", partner_name="James",
        email="sophie@example.com", phone="07700 900456",
    )
    db.add(couple)
    db.flush()
    wedding_day = date.today() + timedelta(days=40)
    booking = Booking(
        brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CONFIRMED,
        title="Sophie & James", client_id=couple.id, event_date=wedding_day,
        venue_or_project="Peckforton Castle", package_name="Gold Package 3",
        quoted_total=Decimal("899"), deposit_amount=Decimal("100"),
        legacy_source="studio_ninja" if imported else None,
        legacy_id="sn-final-call" if imported else None,
        automation_suppressed=imported,
    )
    db.add(booking)
    db.flush()
    db.add(Task(
        booking_id=booking.id, title="Finalise wedding details by phone",
        workflow_key="wbm_final_details_call",
        due_at=datetime.now(timezone.utc) + timedelta(days=10),
    ))
    return booking


def test_complete_final_call_pack_saves_notes_pdf_and_completes_existing_task():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            booking = add_wedding(db)
            db.add(FormSubmission(
                booking_id=booking.id, form_type="booking_form",
                data={
                    "primary_full_name": "Sophie Taylor", "primary_email": "sophie@example.com",
                    "partner_full_name": "James Taylor", "partner_email": "james@example.com",
                    "ceremony_time": "13:00", "ceremony_details": "Peckforton Castle chapel",
                    "reception_details": "Peckforton Castle", "unique_events": "Sparkler exit",
                    "additional_information": "Grandad uses a wheelchair",
                    "highlight_music": "Song one and Song two", "guest_uploads": "Yes please",
                },
            ))
            db.add(FormSubmission(
                booking_id=booking.id, form_type="final_timings",
                data={
                    "ceremony_time": "13:00", "ceremony_venue": "Peckforton Castle chapel",
                    "reception_venue": "Peckforton Castle", "prep_venue": "Castle bridal suite",
                    "prep_notes": "Room available from 10", "second_prep": "None",
                    "extra_stops": "None", "day_contact": "Amy", "day_mobile": "07700 900999",
                    "coordinator": "Sarah", "group_count": "5 groups",
                    "important_notes": "Grandad uses a wheelchair",
                    "_calculation": {
                        "coverage_warning": False, "travel_warning": False,
                        "timeline": [
                            {"time": "11:30", "event": "Preparation photographs", "detail": "Castle bridal suite"},
                            {"time": "13:00", "event": "Ceremony", "detail": "Peckforton Castle chapel"},
                            {"time": "19:30", "event": "First dance", "detail": "Expected coverage finish"},
                        ],
                    },
                },
            ))
            db.add(ContractAcceptance(
                booking_id=booking.id, contract_title="Wedding Agreement", contract_version="Rev 1.4",
                contract_body="Protected agreement", accepted_name="Sophie Taylor",
                accepted_email="sophie@example.com", supplier_signed_name="Mark Adam Powell",
                supplier_signed_at=datetime.now(timezone.utc),
            ))
            db.add(Invoice(
                booking_id=booking.id, brand=Brand.WBM, sequence=9001, number="WBM09001",
                issue_date=date.today(), total=Decimal("899"), paid=Decimal("899"),
                status="paid", description="Gold Package 3",
            ))
            db.commit()
            booking_id = booking.id

        status = client.get(f"/api/bookings/{booking_id}/final-call-pack")
        assert status.status_code == 200, status.text
        assert status.json()["readiness"]["ready"] is True
        assert status.json()["checked_count"] == 0
        assert status.json()["private_only"] is True

        checklist = {key: True for key, _label in CHECKLIST_ITEMS}
        saved = client.put(f"/api/bookings/{booking_id}/final-call-pack", json={
            "checklist": checklist,
            "notes": "Confirmed the 11:30 start and wheelchair access. No further action needed.",
            "completed": True,
        })
        assert saved.status_code == 200, saved.text
        result = saved.json()
        assert result["completed"] is True
        assert result["completed_at"]
        assert result["checked_count"] == len(CHECKLIST_ITEMS)
        assert result["document_id"]

        pdf = client.get(f"/api/bookings/{booking_id}/final-call-pack.pdf")
        assert pdf.status_code == 200, pdf.text
        assert pdf.content.startswith(b"%PDF")
        assert pdf.headers["content-disposition"].startswith("attachment")
        inline = client.get(f"/api/bookings/{booking_id}/final-call-pack.pdf?inline=true")
        assert inline.status_code == 200
        assert inline.headers["content-disposition"].startswith("inline")

        queue = client.get("/api/workflow-queues").json()["queues"]["final_calls"]
        assert all(item["booking_id"] != booking_id for item in queue)
        with SessionLocal() as db:
            booking = db.get(Booking, booking_id)
            task = db.scalar(select(Task).where(
                Task.booking_id == booking_id,
                Task.workflow_key == "wbm_final_details_call",
            ))
            document = db.scalar(select(Document).where(
                Document.booking_id == booking_id,
                Document.category == "final_call_pack",
            ))
            assert task.completed is True
            assert booking.workflow_state["final_call_pack"]["notes"].startswith("Confirmed")
            assert document.is_client_visible is False
            assert document.source_system == "bookingsystem2026_generated"
            assert document.legacy_reference == "final_call_pack:v1"
            assert (TEST_ROOT / "v823-storage" / document.storage_name).read_bytes().startswith(b"%PDF")
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 0
            assert db.scalar(select(func.count()).select_from(ReminderLog)) == 0

        reopened = client.put(f"/api/bookings/{booking_id}/final-call-pack", json={
            "checklist": checklist, "notes": "One follow-up now needed.", "completed": False,
        })
        assert reopened.status_code == 200
        assert reopened.json()["completed"] is False
        queue = client.get("/api/workflow-queues").json()["queues"]["final_calls"]
        row = next(item for item in queue if item["booking_id"] == booking_id)
        assert row["section"] == "Journey"
        assert row["action"] == "open_final_call_pack"
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Document).where(
                Document.booking_id == booking_id,
                Document.category == "final_call_pack",
            )) == 1


def test_studio_ninja_can_use_private_pack_without_enabling_or_sending_anything():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            booking = add_wedding(db, imported=True)
            db.commit()
            booking_id = booking.id

        status = client.get(f"/api/bookings/{booking_id}/final-call-pack")
        assert status.status_code == 200
        assert status.json()["legacy_source"] == "studio_ninja"
        assert status.json()["automation_suppressed"] is True
        assert "Final Wedding Timings have not been submitted" in status.json()["readiness"]["warnings"]

        saved = client.put(f"/api/bookings/{booking_id}/final-call-pack", json={
            "checklist": {"contacts": True},
            "notes": "Private imported-wedding call note",
            "completed": True,
        })
        assert saved.status_code == 200, saved.text
        assert client.get(f"/api/bookings/{booking_id}/final-call-pack.pdf").status_code == 200
        with SessionLocal() as db:
            booking = db.get(Booking, booking_id)
            assert booking.automation_suppressed is True
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 0
            assert db.scalar(select(func.count()).select_from(ReminderLog)) == 0


def test_v823_assets_and_private_wording_are_wired():
    root = Path(__file__).parents[1]
    index = (root / "app/static/index.html").read_text()
    javascript = (root / "app/static/v823.js").read_text()
    dashboard = (root / "app/static/v811.js").read_text()
    assert "/static/v823.css?v=final-call-pack-v8-23" in index
    assert "/static/v823.js?v=final-call-pack-v8-23" in index
    assert "Complete final telephone-call pack" in javascript
    assert "It does not email the couple" in javascript
    assert "Studio Ninja protection remains on" in javascript
    assert "open_final_call_pack" in dashboard


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v823.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v823.db-journal").unlink(missing_ok=True)

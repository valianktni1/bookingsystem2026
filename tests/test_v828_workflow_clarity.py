import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v828.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v828-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v828-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.main import app
from app.models import (Booking, Brand, Client, ContractAcceptance, EmailLog,
                        FormSubmission, Invoice, Quote, RecordKind, RecordStatus, Task)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v828.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v828.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def add_booking(db, title, status=RecordStatus.ENQUIRY, *, imported=False):
    client = Client(first_name=title.split()[0], last_name="Couple",
                    email=f"{title.lower().replace(' ', '-')}@example.com")
    db.add(client)
    db.flush()
    booking = Booking(
        brand=Brand.WBM, kind=RecordKind.WEDDING, status=status,
        title=title, client_id=client.id,
        event_date=date.today() + timedelta(days=180),
        venue_or_project="Test Hall",
        legacy_source="studio_ninja" if imported else None,
        legacy_id=f"legacy-{client.id}" if imported else None,
        automation_suppressed=imported,
    )
    db.add(booking)
    db.flush()
    return booking


def add_accepted_quote(db, booking):
    db.add(Quote(
        booking_id=booking.id, status="accepted", total=Decimal("899.00"),
        deposit_amount=Decimal("100.00"), accepted_at=datetime.now(timezone.utc),
    ))


def add_paid_invoice(db, booking, sequence):
    booking.deposit_paid_date = date.today()
    db.add(Invoice(
        booking_id=booking.id, brand=Brand.WBM, sequence=sequence,
        number=f"WBM9{sequence:04d}", total=Decimal("899.00"),
        paid=Decimal("100.00"), status="part_paid",
    ))


def complete_details(db, booking, *, final_call_complete=False):
    db.add(FormSubmission(
        booking_id=booking.id, form_type="booking_form",
        data={"ceremony_time": "13:00"},
    ))
    db.add(ContractAcceptance(
        booking_id=booking.id,
        contract_title="Wedding Photography Agreement",
        contract_version="2026.08.23-r1", contract_body="Agreement text",
        accepted_name="Client", accepted_email=booking.client.email,
        supplier_signed_name="Mark Adam Powell",
        supplier_signed_at=datetime.now(timezone.utc),
    ))
    db.add(Task(
        booking_id=booking.id, title="Final details call",
        workflow_key="wbm_final_details_call", completed=final_call_complete,
    ))


def test_booking_list_and_detail_use_one_truthful_journey_stage():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            enquiry = add_booking(db, "Stage Enquiry")

            provisional = add_booking(db, "Stage Provisional", RecordStatus.QUOTED)
            add_accepted_quote(db, provisional)

            secured = add_booking(db, "Stage Secured", RecordStatus.CONFIRMED)
            add_accepted_quote(db, secured)
            add_paid_invoice(db, secured, 1)

            details = add_booking(db, "Stage Details", RecordStatus.CONFIRMED)
            add_accepted_quote(db, details)
            add_paid_invoice(db, details, 2)
            complete_details(db, details)

            ready = add_booking(db, "Stage Ready", RecordStatus.CONFIRMED)
            add_accepted_quote(db, ready)
            add_paid_invoice(db, ready, 3)
            complete_details(db, ready, final_call_complete=True)
            db.commit()
            ready_id = ready.id

        response = client.get("/api/bookings")
        assert response.status_code == 200, response.text
        stages = {row["title"]: row["journey_stage"] for row in response.json()}
        assert stages["Stage Enquiry"]["label"] == "New enquiry"
        assert stages["Stage Provisional"]["label"] == "Quote accepted · provisional"
        assert stages["Stage Secured"]["label"] == "Secured"
        assert stages["Stage Details"]["label"] == "Booking details complete"
        assert stages["Stage Ready"]["label"] == "Ready for wedding"

        detail = client.get(f"/api/bookings/{ready_id}")
        assert detail.status_code == 200
        assert detail.json()["journey_stage"] == stages["Stage Ready"]


def test_signed_agreement_is_one_action_and_imported_records_remain_read_only():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            signed = add_booking(db, "Signed Once", RecordStatus.CONFIRMED)
            db.add(FormSubmission(
                booking_id=signed.id, form_type="booking_form", data={"ready": True},
            ))
            db.add(ContractAcceptance(
                booking_id=signed.id, contract_title="Agreement", contract_version="1",
                contract_body="Terms", accepted_name="Signed Client",
                accepted_email=signed.client.email,
            ))
            imported = add_booking(db, "Protected Import", RecordStatus.CONFIRMED,
                                   imported=True)
            db.commit()
            signed_id = signed.id
            imported_id = imported.id

        queues = client.get("/api/workflow-queues")
        assert queues.status_code == 200
        data = queues.json()["queues"]
        assert sum(row["booking_id"] == signed_id for row in data["client_updates"]) == 1
        assert not any(row["booking_id"] == signed_id for row in data["agreements_waiting"])

        records = client.get("/api/bookings").json()
        imported_row = next(row for row in records if row["id"] == imported_id)
        assert imported_row["journey_stage"]["imported"] is True
        assert "general new-system client emails remain paused" in imported_row["journey_stage"]["help"]
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 0


def test_v828_dashboard_and_record_actions_are_explicit_and_mobile_friendly():
    root = Path(__file__).parents[1]
    index = (root / "app/static/index.html").read_text()
    app_js = (root / "app/static/app.js").read_text()
    dashboard_js = (root / "app/static/v811.js").read_text()
    css = (root / "app/static/v811.css").read_text()
    assert "STUDIO MOBILE WORKSPACE V8.30.1" in index
    assert "/static/app.js?v=client-receipt-open-v8-28-4-2" in index
    assert "/static/v811.js?v=studio-style-workspace-v8-30" in index
    assert "Needs your action" in dashboard_js
    assert "Waiting and upcoming" in dashboard_js
    assert "new Set(actionQueueOrder.flatMap" in dashboard_js
    assert "if (next.action) return next" in dashboard_js
    assert 'action:"review_booking_form"' in app_js
    assert 'action:"retry_email"' in app_js
    assert "Studio Ninja handles the existing client messages" in app_js
    assert ".v828-journey-summary" in css
    assert "@media(max-width:560px)" in css


def test_public_enquiry_can_embed_only_on_the_wbm_website():
    reset_database()
    with TestClient(app) as client:
        enquiry = client.get("/enquiry")
        assert enquiry.status_code == 200
        assert "x-frame-options" not in enquiry.headers
        policy = enquiry.headers["content-security-policy"]
        assert policy == (
            "frame-ancestors 'self' https://perfectweddingsbymark.uk "
            "https://www.perfectweddingsbymark.uk"
        )

        private_app = client.get("/dashboard")
        assert private_app.status_code == 200
        assert private_app.headers["x-frame-options"] == "DENY"
        assert "content-security-policy" not in private_app.headers


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v828.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v828.db-journal").unlink(missing_ok=True)

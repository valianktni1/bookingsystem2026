import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v822.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v822-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v822-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.mail_routes import _booking_matches
from app.main import app
from app.models import (Booking, Brand, Client, ContractAcceptance, EmailLog,
                        FormSubmission, RecordKind, RecordStatus, ReminderLog, Task)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v822.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v822.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def add_booking(db, title, email, *, legacy_source=None, suppressed=False):
    client = Client(first_name=title.split()[0], last_name="Couple", email=email)
    db.add(client)
    db.flush()
    booking = Booking(
        brand=Brand.WBM,
        kind=RecordKind.WEDDING,
        status=RecordStatus.CONFIRMED,
        title=title,
        client_id=client.id,
        event_date=date.today() + timedelta(days=90),
        venue_or_project="Test Venue",
        legacy_source=legacy_source,
        legacy_id=f"legacy-{client.id}" if legacy_source else None,
        automation_suppressed=suppressed,
    )
    db.add(booking)
    db.flush()
    return booking


def test_new_client_updates_are_prominent_actionable_and_clear_only_when_dealt_with():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            booking_form = add_booking(db, "Alice & Ben", "alice@example.com")
            timings = add_booking(
                db, "Cara & Dan", "cara@example.com",
                legacy_source="studio_ninja", suppressed=True,
            )
            agreement = add_booking(db, "Emily & Finn", "emily@example.com")
            legacy_agreement = add_booking(
                db, "Grace & Hugo", "grace@example.com",
                legacy_source="studio_ninja", suppressed=True,
            )

            db.add_all([
                FormSubmission(
                    booking_id=booking_form.id,
                    form_type="booking_form",
                    data={"partner_email": "ben@example.com"},
                    submission_source="client_portal",
                    updated_at=datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
                ),
                Task(
                    booking_id=booking_form.id,
                    title="Review submitted Wedding Booking Form",
                    workflow_key="wbm_review_booking_form",
                ),
                FormSubmission(
                    booking_id=timings.id,
                    form_type="final_timings",
                    data={"ceremony_time": "13:00"},
                    submission_source="client_portal_updated",
                    updated_at=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
                ),
                Task(
                    booking_id=timings.id,
                    title="Review final wedding timings",
                    workflow_key="wbm_review_final_timings",
                ),
                ContractAcceptance(
                    booking_id=agreement.id,
                    contract_title="Wedding Photography Agreement",
                    contract_version="2026.08.20-r2",
                    contract_body="Agreement text",
                    accepted_name="Emily Client",
                    accepted_email="emily@example.com",
                    accepted_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
                ),
                ContractAcceptance(
                    booking_id=legacy_agreement.id,
                    contract_title="Imported agreement",
                    contract_version="Studio Ninja",
                    contract_body="Imported text",
                    accepted_name="Grace Client",
                    accepted_email="grace@example.com",
                    is_legacy_import=True,
                ),
            ])
            db.commit()
            booking_form_id = booking_form.id
            timings_id = timings.id
            agreement_id = agreement.id

        response = client.get("/api/workflow-queues")
        assert response.status_code == 200
        updates = response.json()["queues"]["client_updates"]
        assert [item["update_type"] for item in updates] == [
            "agreement", "final_timings", "booking_form",
        ]
        by_type = {item["update_type"]: item for item in updates}
        assert by_type["booking_form"]["action"] == "review_booking_form"
        assert by_type["booking_form"]["section"] == "Journey"
        assert by_type["final_timings"]["action"] == "review_final_timings"
        assert by_type["agreement"]["action"] == "countersign"

        reviewed_form = client.post(f"/api/bookings/{booking_form_id}/booking-form/review")
        reviewed_timings = client.post(f"/api/bookings/{timings_id}/final-timings/review")
        assert reviewed_form.status_code == 200, reviewed_form.text
        assert reviewed_timings.status_code == 200, reviewed_timings.text

        remaining = client.get("/api/workflow-queues").json()["queues"]["client_updates"]
        assert [(item["update_type"], item["booking_id"]) for item in remaining] == [
            ("agreement", agreement_id),
        ]
        with SessionLocal() as db:
            imported = db.get(Booking, timings_id)
            assert imported.automation_suppressed is True
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 0
            assert db.scalar(select(func.count()).select_from(ReminderLog)) == 0


def test_exact_partner_email_matches_booking_but_unrelated_email_does_not():
    reset_database()
    with TestClient(app):
        with SessionLocal() as db:
            booking = add_booking(db, "Ivy & Jack", "ivy@example.com")
            db.add(FormSubmission(
                booking_id=booking.id,
                form_type="booking_form",
                data={"primary_email": "ivy@example.com", "partner_email": "jack@example.com"},
            ))
            db.commit()
            matches = _booking_matches(
                db, {"jack@example.com", "unrelated@example.com"}, Brand.WBM
            )
            assert matches["jack@example.com"].id == booking.id
            assert "unrelated@example.com" not in matches


def test_dashboard_upcoming_weddings_are_booked_wbm_jobs_only_and_date_ordered():
    reset_database()
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            later = add_booking(db, "Dashboard Later Wedding", "later@example.com")
            later.event_date = date.today() + timedelta(days=20)

            sooner = add_booking(db, "Dashboard Sooner Wedding", "sooner@example.com")
            sooner.status = RecordStatus.IN_PROGRESS
            sooner.event_date = date.today() + timedelta(days=10)

            enquiry = add_booking(db, "Dashboard Enquiry", "enquiry@example.com")
            enquiry.status = RecordStatus.ENQUIRY
            enquiry.event_date = date.today() + timedelta(days=5)

            cancelled = add_booking(db, "Dashboard Cancelled", "cancelled@example.com")
            cancelled.status = RecordStatus.CANCELLED
            cancelled.event_date = date.today() + timedelta(days=3)

            ivory = add_booking(db, "Dashboard Ivory Project", "ivory@example.com")
            ivory.brand = Brand.IVORY
            ivory.kind = RecordKind.DIGITAL
            ivory.event_date = date.today() + timedelta(days=1)
            db.commit()

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        dashboard_titles = [
            row["title"] for row in response.json()["upcoming_weddings"]
            if row["title"].startswith("Dashboard ")
        ]
        assert dashboard_titles == ["Dashboard Sooner Wedding", "Dashboard Later Wedding"]


def test_v822_dashboard_assets_and_exact_actions_are_wired():
    root = Path(__file__).parents[1]
    index = (root / "app/static/index.html").read_text()
    dashboard_js = (root / "app/static/v811.js").read_text()
    forms_js = (root / "app/static/v895.js").read_text()
    mail_js = (root / "app/static/v896.js").read_text()
    css = (root / "app/static/v822.css").read_text()
    assert "/static/v822.css?v=client-updates-dashboard-v8-22" in index
    assert "/static/v811.js?v=enquiry-embed-hotfix-v8-28-1" in index
    assert "/static/v895.js?v=client-updates-dashboard-v8-22" in index
    assert "/static/v896.js?v=client-updates-dashboard-v8-22" in index
    assert "New client updates" in dashboard_js
    assert "unread_only=true" in dashboard_js
    assert "openInboxMessageFromDashboard" in mail_js
    assert "I've reviewed this booking form" in forms_js
    assert 'data-queue-jump="client_updates"' in css


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v822.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v822.db-journal").unlink(missing_ok=True)

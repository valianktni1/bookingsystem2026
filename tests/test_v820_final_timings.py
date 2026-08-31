import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v820.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v820-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v820-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main_module
from app.database import SessionLocal, engine
from app.final_timings import STUDIO_NINJA_AUTOMATION_AFTER, studio_ninja_final_timings_email_due
from app.main import app
from app.models import (Booking, Brand, Client, ClientPortalToken, Document, EmailLog,
                        FormSubmission, RecordKind, RecordStatus, ReminderLog, Task)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v820.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v820.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def final_answers():
    return {
        "ceremony_time": "13:00", "ceremony_duration": 45,
        "ceremony_venue": "St Mary's Church, Chester",
        "reception_same": False, "reception_venue": "Oak Hall, Chester",
        "prep_photos": True, "prep_person": "Sophie",
        "prep_venue": "The Hotel, Chester", "travel_minutes": 20,
        "start_choice": "normal", "requested_start": None,
        "prep_notes": "Room 12", "second_prep": None,
        "group_photo_time": "14:30", "meal_time": "16:00",
        "speeches_time": "18:00", "speeches_position": "After the meal",
        "evening_time": "19:00", "cake_time": "19:15",
        "first_dance_time": "19:30", "later_event": False,
        "later_event_name": None, "later_event_time": None,
        "extra_stops": None, "day_contact": "Amy Jones",
        "day_mobile": "07700 900123", "coordinator": "Sarah at Oak Hall",
        "group_count": "1-5", "important_notes": "Grandad uses a wheelchair",
    }


def test_native_final_timings_uses_spare_coverage_and_reopens_review_task():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "confirmed",
            "title": "Sophie & James",
            "client": {"first_name": "Sophie", "last_name": "Taylor",
                       "partner_name": "James", "email": "sophie@example.com",
                       "phone": "07700 900456"},
            "event_date": (date.today() + timedelta(days=30)).isoformat(),
            "venue_or_project": "St Mary's Church", "package_name": "Silver Package 2",
            "quoted_total": 899, "deposit_amount": 100,
        }).json()
        portal = client.post(f"/api/bookings/{booking['id']}/portal", json={"expires_days": 365})
        assert portal.status_code == 201
        token = portal.json()["url"].split("/client/")[1]
        public = client.get(f"/api/client/{token}").json()
        assert public["final_timings"]["available"] is True
        assert public["final_timings"]["coverage"]["allowance_minutes"] == 480

        saved = client.post(f"/api/client/{token}/forms", json={
            "form_type": "final_timings", "data": final_answers(),
        })
        assert saved.status_code == 200, saved.text
        assert client.get(f"/api/bookings/{booking['id']}").json()["form_data"]["ceremony_time"] == "13:00"
        pdf_document_id = saved.json()["pdf_document_id"]
        assert pdf_document_id
        public = client.get(f"/api/client/{token}").json()
        submission = next(x for x in public["submissions"] if x["form_type"] == "final_timings")
        assert submission["source_document_id"] == pdf_document_id
        assert public["final_timings"]["submitted"] is True
        assert public["final_timings"]["submitted_at"] == submission["submitted_at"]
        assert public["final_timings"]["pdf_document_id"] == pdf_document_id
        calculation = submission["data"]["_calculation"]
        assert calculation["suggested_start"] == "11:30"
        assert calculation["prep_departure"] == "12:25"
        assert calculation["prep_window_minutes"] == 55
        assert calculation["coverage_minutes"] == 480
        assert calculation["coverage_warning"] is False
        assert calculation["earlier_start_minutes"] == 30

        pdf = client.get(f"/api/bookings/{booking['id']}/final-timings.pdf")
        assert pdf.status_code == 200, pdf.text
        assert pdf.content.startswith(b"%PDF")
        assert pdf.headers["content-disposition"].startswith("attachment")
        inline_pdf = client.get(f"/api/bookings/{booking['id']}/final-timings.pdf?inline=true")
        assert inline_pdf.status_code == 200
        assert inline_pdf.headers["content-disposition"].startswith("inline")
        record_documents = client.get(f"/api/bookings/{booking['id']}").json()["documents"]
        assert any(item["id"] == pdf_document_id and item["category"] == "final_timings"
                   for item in record_documents)
        with SessionLocal() as db:
            document = db.get(Document, pdf_document_id)
            assert document.category == "final_timings"
            assert document.source_system == "bookingsystem2026_generated"
            assert document.is_client_visible is False
            assert document.original_name == "Final Wedding Timings - Sophie & James.pdf"
            assert (TEST_ROOT / "v820-storage" / document.storage_name).read_bytes().startswith(b"%PDF")

        reviewed = client.post(f"/api/bookings/{booking['id']}/final-timings/review")
        assert reviewed.status_code == 200
        assert client.get(f"/api/bookings/{booking['id']}/portal").json()["final_timings"]["reviewed_at"]

        changed = final_answers()
        changed["first_dance_time"] = "19:45"
        changed_response = client.post(f"/api/client/{token}/forms", json={
            "form_type": "final_timings", "data": changed,
        })
        assert changed_response.status_code == 200
        assert changed_response.json()["pdf_document_id"] == pdf_document_id
        refreshed = client.get(f"/api/bookings/{booking['id']}/portal").json()
        assert refreshed["final_timings"]["reviewed_at"] is None
        with SessionLocal() as db:
            task = db.scalar(select(Task).where(
                Task.booking_id == booking["id"],
                Task.workflow_key == "wbm_review_final_timings",
            ))
            assert task is not None and task.completed is False
            documents = db.scalars(select(Document).where(
                Document.booking_id == booking["id"],
                Document.category == "final_timings",
            )).all()
            assert [item.id for item in documents] == [pdf_document_id]


def test_bronze_genuine_overrun_is_visible_but_does_not_change_booking():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "confirmed",
            "title": "Bronze Couple",
            "client": {"first_name": "Alex", "last_name": "Brown", "email": "alex@example.com"},
            "event_date": (date.today() + timedelta(days=30)).isoformat(),
            "venue_or_project": "Oak Hall", "package_name": "Bronze Package 1",
            "quoted_total": 499, "deposit_amount": 100,
        }).json()
        token = client.post(f"/api/bookings/{booking['id']}/portal", json={"expires_days": 365}).json()["url"].split("/client/")[1]
        assert client.post(f"/api/client/{token}/forms", json={
            "form_type": "final_timings", "data": final_answers(),
        }).status_code == 200
        public = client.get(f"/api/client/{token}").json()
        calculation = next(x for x in public["submissions"] if x["form_type"] == "final_timings")["data"]["_calculation"]
        assert calculation["coverage_warning"] is True
        assert calculation["over_standard_minutes"] == 210
        assert calculation["additional_hours_suggested"] == 4
        unchanged = client.get(f"/api/bookings/{booking['id']}").json()
        assert unchanged["package_name"] == "Bronze Package 1"
        assert unchanged["quoted_total"] == 499


def test_studio_ninja_has_exactly_one_eligible_automatic_email(monkeypatch):
    reset_database()
    frozen_today = date(2026, 10, 1)

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return frozen_today

    delivered = []
    monkeypatch.setattr(main_module, "date", FrozenDate)
    monkeypatch.setattr(main_module, "send_booking_template_email",
                        lambda db, booking, profile, template, portal_url=None, **kwargs:
                        (template.subject, delivered.append((booking.id, template.template_key, portal_url)) or template.body))

    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            eligible_client = Client(first_name="Eligible", last_name="Couple", email="eligible@example.com")
            too_early_client = Client(first_name="Later", last_name="Couple", email="later@example.com")
            manual_client = Client(first_name="Manual", last_name="Couple", email="manual@example.com")
            db.add_all([eligible_client, too_early_client, manual_client]); db.flush()
            eligible = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CONFIRMED,
                title="Eligible SN Couple", client_id=eligible_client.id,
                event_date=date(2026, 10, 31), package_name="Gold Package 3",
                legacy_source="studio_ninja", legacy_id="sn-eligible",
                automation_suppressed=True,
            )
            not_due = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CONFIRMED,
                title="Not Due SN Couple", client_id=too_early_client.id,
                event_date=frozen_today + timedelta(days=120), package_name="Gold Package 3",
                legacy_source="studio_ninja", legacy_id="sn-not-due",
                automation_suppressed=True,
            )
            manual = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CONFIRMED,
                title="Pre-cutoff manual SN Couple", client_id=manual_client.id,
                event_date=STUDIO_NINJA_AUTOMATION_AFTER, package_name="Gold Package 3",
                legacy_source="studio_ninja", legacy_id="sn-manual",
                automation_suppressed=True,
            )
            db.add_all([eligible, not_due, manual]); db.commit()
            eligible_id, not_due_id, manual_id = eligible.id, not_due.id, manual.id

            assert main_module.run_due_reminders(db) == {"sent": 1, "skipped": 0, "failed": 0}
            assert main_module.run_due_reminders(db) == {"sent": 0, "skipped": 1, "failed": 0}
            assert delivered == [(eligible_id, "check_in_30", delivered[0][2])]
            assert "?tab=timings" in delivered[0][2]
            assert db.scalars(select(EmailLog).where(EmailLog.booking_id == eligible_id)).all()[0].template_key == "check_in_30"
            assert db.scalars(select(ReminderLog).where(ReminderLog.booking_id == not_due_id)).all() == []
            assert db.scalars(select(ClientPortalToken).where(ClientPortalToken.booking_id == not_due_id)).all() == []

        opened = client.post(f"/api/bookings/{manual_id}/final-details", json={
            "unlocked": True,
            "reason": "Opened early to send the Final Wedding Timings Form",
        })
        assert opened.status_code == 200, opened.text
        sent = client.post(f"/api/bookings/{manual_id}/emails/send", json={
            "template_key": "check_in_30",
            "manual_confirmation": "SEND ONE MANUAL EMAIL",
            "manual_reason": "Final Wedding Timings Form deliberately sent early",
        })
        assert sent.status_code == 200, sent.text
        assert sent.json()["manual_only"] is True
        assert sent.json()["automation_suppressed"] is True
        assert delivered[-1][0:2] == (manual_id, "check_in_30")
        assert "?tab=timings" in delivered[-1][2]
        assert client.get(f"/api/bookings/{manual_id}/portal").json()["final_timings"]["available"] is True
        with SessionLocal() as db:
            manual_booking = db.get(Booking, manual_id)
            manual_logs = db.scalars(select(EmailLog).where(EmailLog.booking_id == manual_id)).all()
            assert manual_booking.automation_suppressed is True
            assert [item.template_key for item in manual_logs] == ["check_in_30"]

    boundary = Booking(
        brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.CONFIRMED,
        event_date=STUDIO_NINJA_AUTOMATION_AFTER, legacy_source="studio_ninja",
    )
    assert studio_ninja_final_timings_email_due(
        boundary, STUDIO_NINJA_AUTOMATION_AFTER - timedelta(days=30)
    ) is False


def test_v820_assets_and_old_final_questionnaire_remain_blocked():
    root = Path(__file__).parents[1]
    index = (root / "app/static/index.html").read_text()
    client_html = (root / "app/static/client.html").read_text()
    assert "/static/v820.js?v=final-timings-pdf-download-v8-33-1" in index
    assert "/static/client-v820.js?v=durable-form-drafts-v8-29" in client_html
    assert "only automatic email permitted" in (root / "app/main.py").read_text()
    assert 'pattern="^(booking_form|final_timings)$"' in (root / "app/schemas.py").read_text()
    admin_js = (root / "app/static/v820.js").read_text()
    assert "Send timings form now" in admin_js
    assert "Open & send form now" in admin_js
    assert 'host.querySelectorAll(".v820-final")' in admin_js
    assert "SEND ONE MANUAL EMAIL" in admin_js
    assert "View complete form" in admin_js
    assert "View / download PDF" in admin_js
    assert "A PDF copy is retained automatically in Files" in admin_js


def test_v8232_mobile_submission_cannot_fail_silently_and_restores_draft():
    root = Path(__file__).parents[1]
    client_html = (root / "app/static/client.html").read_text()
    client_js = (root / "app/static/client-v820.js").read_text()
    client_css = (root / "app/static/client-v820.css").read_text()

    assert "/static/client-v820.css?v=durable-form-drafts-v8-29" in client_html
    assert '<form id="final-timings-form" novalidate>' in client_js
    assert "localStorage.setItem(timingsDraftKey(),payload)" in client_js
    assert "localStorage.removeItem(timingsDraftKey())" in client_js
    assert "sessionStorage.getItem(key)" in client_js
    assert "TIMINGS_DRAFT_MAX_AGE" in client_js
    assert "const invalid=firstInvalid();" in client_js
    assert "steps.indexOf(step)" in client_js
    assert "Sending securely…" in client_js
    assert "if(submitting)return" in client_js
    assert 'role="alert"' in client_js
    assert '[aria-invalid="true"]' in client_css


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v820.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v820.db-journal").unlink(missing_ok=True)

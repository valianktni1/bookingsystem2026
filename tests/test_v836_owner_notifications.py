import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v836.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v836-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v836-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main_module
import app.owner_notifications as owner_module
from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, Brand, Client, EmailLog, RecordKind, RecordStatus
from app.owner_notifications import OWNER_NOTIFICATION_KEYS


WEDDING_DATE = date.today() + timedelta(days=30)


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v836.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v836.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def booking_form_answers():
    return {
        "primary_full_name": "Sophie Taylor", "primary_phone": "07700 900123",
        "primary_email": "sophie@example.com", "partner_full_name": "James Taylor",
        "street_address": "1 Test Road", "town": "Knutsford", "county": "Cheshire",
        "postcode": "WA16 0AA", "wedding_date": WEDDING_DATE.isoformat(),
        "ceremony_time": "13:00", "ceremony_details": "Peckforton Castle ceremony",
        "reception_details": "Peckforton Castle reception",
        "package_selected": "Gold Package 3 2026/27/28", "payment_plan": "standard",
        "wedding_party_size": "8", "unique_events": "None",
    }


def final_timings_answers():
    return {
        "ceremony_time": "13:00", "ceremony_duration": 45,
        "ceremony_venue": "Peckforton Castle, Cheshire",
        "reception_same": True, "reception_venue": None,
        "prep_photos": True, "prep_person": "Sophie",
        "prep_venue": "Peckforton Castle", "travel_minutes": 0,
        "start_choice": "normal", "requested_start": None,
        "prep_notes": "Room 12", "second_prep": None,
        "group_photo_time": "14:30", "meal_time": "16:00",
        "speeches_time": "18:00", "speeches_position": "After the meal",
        "evening_time": "19:00", "cake_time": "19:15",
        "first_dance_time": "19:30", "later_event": False,
        "later_event_name": None, "later_event_time": None,
        "extra_stops": None, "day_contact": "Amy Jones",
        "day_mobile": "07700 900456", "coordinator": "Venue manager",
        "group_count": "1-5", "important_notes": "No additional notes",
    }


def test_all_client_progress_steps_email_mark_and_remain_private(monkeypatch):
    reset_database()
    delivered = []
    monkeypatch.setattr(owner_module, "smtp_ready", lambda brand=None: True)

    def fake_owner_email(booking, profile, recipient, subject, body,
                         open_tracking_url=None, reply_to=None):
        delivered.append({
            "recipient": recipient, "subject": subject, "body": body,
            "reply_to": reply_to, "tracking": open_tracking_url,
        })

    monkeypatch.setattr(owner_module, "send_rendered_email", fake_owner_email)

    with TestClient(app) as client:
        login(client)
        created = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "enquiry",
            "title": "Sophie & James",
            "client": {
                "first_name": "Sophie", "last_name": "Taylor",
                "partner_name": "James", "email": "sophie@example.com",
            },
            "event_date": WEDDING_DATE.isoformat(),
            "venue_or_project": "Peckforton Castle",
            "quoted_total": 0, "deposit_amount": 0,
        }).json()
        portal = client.post(
            f"/api/bookings/{created['id']}/portal", json={"expires_days": 365},
        ).json()
        token = portal["url"].split("/client/")[1]
        catalog = client.get("/api/public/catalog").json()
        gold = next(row for row in catalog["packages"] if row["code"] == "gold")

        accepted = client.post(f"/api/client/{token}/quote", json={
            "package_id": gold["id"], "addon_ids": [], "confirmed": True,
        })
        assert accepted.status_code == 201, accepted.text

        form = client.post(f"/api/client/{token}/forms", json={
            "form_type": "booking_form", "data": booking_form_answers(),
        })
        assert form.status_code == 200, form.text

        with SessionLocal() as db:
            booking = db.get(Booking, created["id"])
            booking.status = RecordStatus.CONFIRMED
            db.commit()

        timings = client.post(f"/api/client/{token}/forms", json={
            "form_type": "final_timings", "data": final_timings_answers(),
        })
        assert timings.status_code == 200, timings.text

        contract = client.post(f"/api/client/{token}/contract", json={
            "accepted_name": "Sophie Taylor", "accepted_email": "sophie@example.com",
            "agreed": True,
        })
        assert contract.status_code == 200, contract.text

        assert len(delivered) == 4
        assert all(row["recipient"] == "mark@example.com" for row in delivered)
        assert all(row["reply_to"] == "sophie@example.com" for row in delivered)
        assert all(row["tracking"] is None for row in delivered)
        assert "Quote accepted" in delivered[0]["subject"]
        assert "Wedding Booking Form submitted" in delivered[1]["subject"]
        assert "Final Wedding Timings submitted" in delivered[2]["subject"]
        assert "Wedding agreement signed" in delivered[3]["subject"]
        assert all(f"/bookings/{created['id']}/" in row["body"] for row in delivered)

        with SessionLocal() as db:
            owner_logs = db.scalars(select(EmailLog).where(
                EmailLog.booking_id == created["id"],
                EmailLog.template_key.in_(tuple(OWNER_NOTIFICATION_KEYS)),
            )).all()
            assert {row.template_key for row in owner_logs} == {
                "quote_accepted_admin", "booking_form_submitted_admin",
                "final_timings_submitted_admin", "contract_signed_admin",
            }
            assert all(row.status == "sent" for row in owner_logs)

        public = client.get(f"/api/client/{token}").json()
        assert not OWNER_NOTIFICATION_KEYS.intersection(
            {row["template_key"] for row in public["emails"]}
        )
        updates = client.get("/api/workflow-queues").json()["queues"]["client_updates"]
        update_types = {row["update_type"] for row in updates}
        assert {"quote_accepted", "booking_form", "final_timings", "agreement_completed"} <= update_types


def test_failed_private_notification_never_undoes_action_and_can_be_retried(monkeypatch):
    reset_database()
    monkeypatch.setattr(owner_module, "smtp_ready", lambda brand=None: True)
    monkeypatch.setattr(
        owner_module, "send_rendered_email",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Temporary SMTP problem")),
    )
    with TestClient(app) as client:
        login(client)
        with SessionLocal() as db:
            person = Client(first_name="Retry", last_name="Couple", email="retry@example.com")
            db.add(person)
            db.flush()
            booking = Booking(
                brand=Brand.WBM, kind=RecordKind.WEDDING, status=RecordStatus.QUOTED,
                title="Retry & Couple", client_id=person.id,
                event_date=WEDDING_DATE, package_name="Gold Package",
                quoted_total=899, deposit_amount=100,
            )
            db.add(booking)
            db.commit()
            booking_id = booking.id
            result = owner_module.send_owner_notification_safely(
                db, booking, "quote_accepted_admin", section="payments",
                extra_values={
                    "invoice_number": "WBM02099", "accepted_package": "Gold Package",
                    "accepted_addons": "No additional items",
                },
            )
            assert result["status"] == "failed"
            assert db.get(Booking, booking_id).status == RecordStatus.QUOTED
            failure = db.scalar(select(EmailLog).where(
                EmailLog.booking_id == booking_id,
                EmailLog.template_key == "quote_accepted_admin",
            ))
            assert failure.status == "failed"
            failure_id = failure.id

        queue = client.get("/api/workflow-queues").json()["queues"]["communication_failures"]
        private_failure = next(row for row in queue if row["failure_id"] == failure_id)
        assert private_failure["private_owner_notification"] is True
        assert "Private notification to Mark" in private_failure["detail"]

        retried = []
        monkeypatch.setattr(
            main_module, "send_rendered_email",
            lambda *args, **kwargs: retried.append((args, kwargs)),
        )
        response = client.post(f"/api/communications/failures/email/{failure_id}/retry")
        assert response.status_code == 200, response.text
        assert len(retried) == 1
        assert retried[0][1]["reply_to"] == "retry@example.com"
        assert retried[0][1]["open_tracking_url"] is None


def test_v836_templates_usage_cache_busting_and_build_markers():
    root = Path(__file__).parents[1]
    bootstrap = (root / "app/bootstrap.py").read_text()
    main = (root / "app/main.py").read_text()
    dashboard = (root / "app/static/v811.js").read_text()
    index = (root / "app/static/index.html").read_text()
    for key in (
        "quote_accepted_admin", "booking_form_submitted_admin",
        "final_timings_submitted_admin", "contract_signed_admin",
    ):
        assert key in bootstrap
        assert key in main or key in (root / "app/owner_notifications.py").read_text()
    assert "OWNER PROGRESS ALERTS V8.36" in index
    assert "/static/v811.js?v=owner-progress-notifications-v8-36" in index
    assert "Quote acceptances, forms, signed agreements and replies" in dashboard
    assert "Retry this private notification to Mark now?" in dashboard


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v836.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v836.db-journal").unlink(missing_ok=True)

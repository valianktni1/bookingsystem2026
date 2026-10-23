import os
import subprocess
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


TEST_ROOT = Path(__file__).parent
ROOT = TEST_ROOT.parent
DB_FILE = TEST_ROOT / "test-v846.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v846-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"


from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.main as main_module
from app.database import SessionLocal, engine
from app.main import app
from app.models import AuditLog, Booking, EmailLog, Invoice, Quote


def reset_database():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v846.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com",
        "password": "SecureTestPassword!123",
    }).status_code == 200


def create_past_wedding(client, *, title="Delivery Test Couple", legacy=False):
    response = client.post("/api/bookings", json={
        "brand": "wbm",
        "kind": "wedding",
        "status": "confirmed",
        "title": title,
        "client": {
            "first_name": title.split()[0],
            "last_name": "Client",
            "partner_name": "Partner Client",
            "email": f"{title.split()[0].lower()}-v846@example.com",
        },
        "event_date": (date.today() - timedelta(days=3)).isoformat(),
        "venue_or_project": "After Wedding Hall",
        "package_name": "Gold photo and video package",
        "quoted_total": 1019,
        "deposit_amount": 100,
    })
    assert response.status_code == 201, response.text
    booking = response.json()
    with SessionLocal() as db:
        row = db.get(Booking, booking["id"])
        if legacy:
            row.legacy_source = "studio_ninja"
            row.legacy_id = f"legacy-{row.id}"
            row.automation_suppressed = True
        db.add(Quote(
            booking_id=row.id,
            status="accepted",
            total=Decimal("1019"),
            deposit_amount=Decimal("100"),
            line_items=[
                {"type": "package", "name": "Gold package", "description": "Photography and highlight video", "total": 899},
                {"type": "addon", "name": "Wedding album", "description": "Wedding album", "total": 120},
            ],
        ))
        db.commit()
    return booking


def delivered_payload(*, album_status="delivered"):
    return {
        "photos_status": "delivered",
        "photos_delivered_on": date.today().isoformat(),
        "gallery_url": "https://weddingsbymark.uk/gallery/test-couple",
        "video_status": "delivered",
        "video_delivered_on": date.today().isoformat(),
        "video_url": "https://weddingsbymark.uk/gallery/test-couple/video",
        "album_status": album_status,
        "album_delivered_on": date.today().isoformat() if album_status == "delivered" else None,
        "album_notes": "Couple approved the design",
    }


def test_completion_is_one_deliberate_action_and_keeps_optional_tracking():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = create_past_wedding(client)
        invoice = client.post(f"/api/bookings/{booking['id']}/invoices", json={
            "total": 1019,
            "paid": 1019,
            "issue_date": (date.today() - timedelta(days=100)).isoformat(),
            "description": "Gold wedding package and album",
        })
        assert invoice.status_code == 201, invoice.text
        original_invoice = invoice.json()

        initial = client.get(f"/api/bookings/{booking['id']}/after-wedding")
        assert initial.status_code == 200
        assert initial.json()["state"]["photos"]["status"] == "pending"
        assert initial.json()["state"]["video"]["status"] == "pending"
        assert initial.json()["state"]["album"]["status"] == "awaiting_selection"
        assert initial.json()["readiness"]["ready_to_complete"] is False
        with SessionLocal() as db:
            emails_before = db.scalar(select(func.count()).select_from(EmailLog))
        completed = client.post(f"/api/bookings/{booking['id']}/complete")
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "completed"
        open_items = completed.json()["workflow_state"]["completion"]["open_items_at_completion"]
        assert "Photographs delivered" in open_items
        assert "Video delivered or not required" in open_items
        assert "Album delivered or not required" in open_items
        retained_invoice = next(
            row for row in completed.json()["invoices"] if row["id"] == original_invoice["id"]
        )
        assert retained_invoice["number"] == original_invoice["number"]
        assert retained_invoice["paid"] == original_invoice["paid"]

        ordered = client.put(
            f"/api/bookings/{booking['id']}/after-wedding",
            json=delivered_payload(album_status="ordered"),
        )
        assert ordered.status_code == 200, ordered.text
        assert ordered.json()["readiness"]["ready_to_complete"] is True
        assert "Album delivered or not required" in ordered.json()["readiness"]["blockers"]
        assert ordered.json()["state"]["album"]["status_label"] == "Ordered from supplier"

        ready = client.put(
            f"/api/bookings/{booking['id']}/after-wedding",
            json=delivered_payload(),
        )
        assert ready.status_code == 200, ready.text
        assert ready.json()["readiness"]["ready_to_complete"] is True
        assert ready.json()["readiness"]["completed_count"] == 4

        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(EmailLog)) == emails_before
            assert db.scalar(select(AuditLog).where(
                AuditLog.entity_id == booking["id"],
                AuditLog.action == "update_after_wedding_workflow",
            )) is not None

        reopened = client.post(f"/api/bookings/{booking['id']}/reopen-completed")
        assert reopened.status_code == 200
        retained = client.get(f"/api/bookings/{booking['id']}/after-wedding").json()
        assert retained["state"]["photos"]["status"] == "delivered"
        assert retained["state"]["album"]["status"] == "delivered"


def test_review_request_is_reviewed_manual_and_recorded_only_after_success(monkeypatch):
    reset_database()
    delivered = []

    def fake_send(db, booking, profile, template, portal_url=None, **kwargs):
        delivered.append({
            "booking_id": booking.id,
            "recipient": booking.client.email,
            "subject": template.subject,
            "body": template.body,
            "portal_url": portal_url,
        })
        return template.subject, template.body, "review-tracking-hash"

    monkeypatch.setattr(main_module, "send_tracked_booking_template_email", fake_send)
    with TestClient(app) as client:
        login(client)
        booking = create_past_wedding(client, title="Review Test Couple")
        assert client.put(
            f"/api/bookings/{booking['id']}/after-wedding",
            json=delivered_payload(),
        ).status_code == 200
        centre = client.get(f"/api/bookings/{booking['id']}/email-centre").json()
        template = next(
            row for row in centre["templates"] if row["template_key"] == "review_request"
        )
        before = client.get(f"/api/bookings/{booking['id']}/after-wedding").json()
        assert before["state"]["review_request"]["status"] == "not_requested"
        assert delivered == []

        sent = client.post(f"/api/bookings/{booking['id']}/email-centre/send", json={
            "mode": "template",
            "template_key": "review_request",
            "subject": "Thank you - a small favour",
            "body": template["body"] + "\n\nPersonal note for this couple.",
        })
        assert sent.status_code == 200, sent.text
        assert len(delivered) == 1
        after = client.get(f"/api/bookings/{booking['id']}/after-wedding").json()
        assert after["state"]["review_request"]["status"] == "sent"
        assert after["state"]["review_request"]["subject"] == "Thank you - a small favour"
        with SessionLocal() as db:
            log = db.scalar(select(EmailLog).where(
                EmailLog.booking_id == booking["id"],
                EmailLog.template_key == "review_request",
            ))
            assert log is not None and log.status == "sent"
            assert db.scalar(select(AuditLog).where(
                AuditLog.entity_id == booking["id"],
                AuditLog.action == "send_review_request",
            )) is not None


def test_outstanding_balance_is_retained_and_audited_but_does_not_block_completion():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = create_past_wedding(client, title="Balance Test Couple")
        invoice = client.post(f"/api/bookings/{booking['id']}/invoices", json={
            "total": 1019,
            "paid": 100,
            "issue_date": (date.today() - timedelta(days=100)).isoformat(),
            "description": "Gold wedding package and album",
        })
        assert invoice.status_code == 201, invoice.text
        invoice_id = invoice.json()["id"]
        assert client.put(
            f"/api/bookings/{booking['id']}/after-wedding",
            json=delivered_payload(),
        ).status_code == 200

        waiting = client.get(f"/api/bookings/{booking['id']}/after-wedding").json()
        assert waiting["readiness"]["outstanding_balance"] == 919
        assert waiting["readiness"]["ready_to_complete"] is False
        completed = client.post(f"/api/bookings/{booking['id']}/complete")
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "completed"
        completion = completed.json()["workflow_state"]["completion"]
        assert "Account balance clear" in completion["open_items_at_completion"]
        retained_invoice = next(row for row in completed.json()["invoices"] if row["id"] == invoice_id)
        assert retained_invoice["balance"] == 919

        payment = client.post(f"/api/invoices/{invoice_id}/payments", json={
            "amount": 919,
            "paid_date": date.today().isoformat(),
            "payment_type": "bank_transfer",
            "reference": "V846-BALANCE-CLEAR",
        })
        assert payment.status_code == 201, payment.text
        ready = client.get(f"/api/bookings/{booking['id']}/after-wedding").json()
        assert ready["readiness"]["outstanding_balance"] == 0
        assert ready["readiness"]["ready_to_complete"] is True
        assert client.post(f"/api/bookings/{booking['id']}/complete").status_code == 200


def test_studio_ninja_delivery_tracking_stays_manual_only():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = create_past_wedding(client, title="Legacy Delivery Couple", legacy=True)
        tracked = client.put(
            f"/api/bookings/{booking['id']}/after-wedding",
            json=delivered_payload(album_status="not_required"),
        )
        assert tracked.status_code == 200
        assert tracked.json()["manual_only"] is True
        centre = client.get(f"/api/bookings/{booking['id']}/email-centre").json()
        template = next(
            row for row in centre["templates"] if row["template_key"] == "review_request"
        )
        blocked = client.post(f"/api/bookings/{booking['id']}/email-centre/send", json={
            "mode": "template",
            "template_key": "review_request",
            "subject": template["subject"],
            "body": template["body"],
        })
        assert blocked.status_code == 422
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 0


def test_v846_assets_and_manual_controls_are_loaded_last():
    index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/v846.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/v846.css").read_text(encoding="utf-8")
    assert "/static/v846.css?v=after-wedding-v8-46" in index
    assert "/static/v846.js?v=post-wedding-review-14-days" in index
    assert index.rfind("/static/v846.js") > index.rfind("/static/v845.js")
    assert "Update delivery &amp; album" in script
    assert "Review & send review request" in script
    assert "This copy is sent only when you press Send review request" in script
    assert "They never block Mark wedding complete" in script
    assert "Completion is controlled by the single Mark wedding complete button above." in script
    assert "data-v846-complete" not in script
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in css


def test_client_must_deliberately_choose_a_package_while_required_extras_remain():
    script = (ROOT / "app/static/client.js").read_text(encoding="utf-8")
    page = (ROOT / "app/static/client.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/client.css").read_text(encoding="utf-8")
    assert 'name="package_id" value="${item.id}">' in script
    assert 'index === 0 ? "checked" : ""' not in script
    assert "No package has been selected for you" in script
    assert "Choose a package first" in script
    assert 'if (!form.get("package_id"))' in script
    assert 'class="addon-card required-addon"><input type="checkbox" checked disabled>' in script
    assert "/static/client.js?v=package-choice-v8-46" in page
    assert "/static/client.css?v=package-choice-v8-46" in page
    assert ".primary:disabled" in css


def test_wedding_dates_show_the_full_weekday_in_lists_and_the_couple_workspace():
    app_js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    workspace_js = (ROOT / "app/static/v895.js").read_text(encoding="utf-8")
    wedding_list_js = (ROOT / "app/static/v830.js").read_text(encoding="utf-8")
    mobile_js = (ROOT / "app/static/v8301.js").read_text(encoding="utf-8")
    final_js = (ROOT / "app/static/v846.js").read_text(encoding="utf-8")
    assert "function fmtEventDate" in app_js
    assert 'weekday:"long"' in app_js
    assert "fmtEventDate(record.event_date)" in wedding_list_js
    assert "fmtEventDate(record.event_date)" in mobile_js
    assert workspace_js.count("fmtEventDate(r.event_date)") >= 3
    assert 'dateCell.textContent = fmtEventDate(record.event_date)' in final_js

    date_helpers = app_js[:app_js.index("function money")]
    result = subprocess.run(
        ["node", "-e", f'{date_helpers}\nprocess.stdout.write(fmtEventDate("2026-09-10"));'],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.startswith("Thursday,")
    assert result.stdout.endswith("2026")


def teardown_module():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v846.db-journal").unlink(missing_ok=True)

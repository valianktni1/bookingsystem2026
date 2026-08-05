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
from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.main import app
from app.models import ClientPortalToken, EmailLog, FormSubmission, ReminderLog


def legacy_payload():
    return {
        "confirmation": "IMPORT WITHOUT EMAILS",
        "record": {
            "legacy_id": "studio-job-2754576",
            "import_batch": "dry-run-live-58",
            "title": "Sinead & Liam",
            "status": "confirmed",
            "event_date": (date.today() + timedelta(days=120)).isoformat(),
            "venue_or_project": "Test Wedding Hall",
            "venue_address": "1 Wedding Lane, Manchester",
            "package_name": "Gold Package 3 2026/27/28",
            "quoted_total": 1019,
            "deposit_amount": 100,
            "balance_due_date": (date.today() + timedelta(days=75)).isoformat(),
            "notes": "Imported test record",
            "client": {
                "first_name": "Sinead",
                "last_name": "Jones",
                "partner_name": "Liam Jones",
                "email": "sinead@example.com",
                "phone": "07700 900777",
                "address": "Manchester",
            },
            "quote": {
                "legacy_number": "Q-2754576",
                "accepted_at": "2025-03-15T10:30:00+00:00",
                "line_items": [{
                    "type": "package", "name": "Gold Package 3 2026/27/28",
                    "description": "Full day photography and highlight video",
                    "quantity": 1, "unit_price": 899, "total": 899,
                }, {
                    "type": "addon", "name": "Wedding album offer",
                    "description": "Wedding album", "quantity": 1,
                    "unit_price": 120, "total": 120,
                }],
                "total": 1019,
                "deposit_amount": 100,
            },
            "invoice": {
                "legacy_number": "WBM01706",
                "legacy_quote_number": "Q-2754576",
                "issue_date": "2025-03-15",
                "deposit_due_date": "2025-03-16",
                "supply_date": (date.today() + timedelta(days=120)).isoformat(),
                "due_date": (date.today() + timedelta(days=75)).isoformat(),
                "description": "Gold wedding package and album",
                "total": 1019,
                "line_items": [{
                    "name": "Gold Package 3 2026/27/28", "description": "Full package wording",
                    "quantity": 1, "unit_price": 899, "total": 899,
                }, {
                    "name": "Wedding album offer", "description": "Album add-on",
                    "quantity": 1, "unit_price": 120, "total": 120,
                }],
                "payment_schedule": [{
                    "label": "Booking fee", "amount": 100,
                    "due_date": "2025-03-16", "status": "paid",
                }, {
                    "label": "Final balance", "amount": 919,
                    "due_date": (date.today() + timedelta(days=75)).isoformat(),
                    "status": "scheduled",
                }],
                "payments": [{
                    "amount": 50, "paid_date": "2025-03-15",
                    "reference": "WBM01706", "legacy_reference": "payment-1",
                }, {
                    "amount": 50, "paid_date": "2025-03-22",
                    "reference": "WBM01706", "legacy_reference": "payment-2",
                }],
            },
            "booking_form": {
                "data": {
                    "primary_full_name": "Sinead Jones",
                    "partner_full_name": "Liam Jones",
                    "ceremony_time": "13:00",
                },
                "submitted_at": "2025-03-15T11:00:00+00:00",
            },
            "contract": {
                "accepted_at": "2025-03-15T11:00:00+00:00",
                "accepted_name": "Sinead Jones",
                "accepted_email": "sinead@example.com",
                "date_source": "questionnaire_completed_date",
                "source_detail": "Questionnaire completed 15 March 2025; original PDF retained",
            },
            "legacy_timeline": [{
                "date": "2025-03-15", "type": "quote_accepted",
                "detail": "Studio Ninja quote accepted",
            }],
        },
    }


def test_v84_protected_legacy_import_and_brand_counters():
    db_file = TEST_ROOT / "test.db"
    engine.dispose()
    db_file.unlink(missing_ok=True)
    (db_file.parent / "test.db-journal").unlink(missing_ok=True)

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200

        readiness = client.get("/api/legacy-import/readiness")
        assert readiness.status_code == 200
        assert readiness.json()["mode"] == "protected_no_email"

        payload = legacy_payload()
        wrong = dict(payload)
        wrong["confirmation"] = "IMPORT"
        assert client.post("/api/legacy-import/validate", json=wrong).status_code == 422
        validated = client.post("/api/legacy-import/validate", json=payload)
        assert validated.status_code == 200
        assert validated.json()["emails_will_be_sent"] is False

        imported = client.post("/api/legacy-import/records", json=payload)
        assert imported.status_code == 201, imported.text
        result = imported.json()
        assert result["invoice_number"] == "WBM02001"
        assert result["legacy_invoice_number"] == "WBM01706"
        assert result["automation_suppressed"] is True
        booking_id = result["booking_id"]

        record = client.get(f"/api/bookings/{booking_id}").json()
        assert record["legacy_source"] == "studio_ninja"
        assert record["legacy_timeline"][0]["type"] == "quote_accepted"
        invoice = record["invoices"][0]
        assert invoice["legacy_number"] == "WBM01706"
        assert invoice["legacy_quote_number"] == "Q-2754576"
        assert invoice["paid"] == 100
        assert len(invoice["payments"]) == 2
        assert len(invoice["payment_schedule"]) == 2

        portal_status = client.get(f"/api/bookings/{booking_id}/portal").json()
        assert portal_status["automation_suppressed"] is True
        assert portal_status["final_details_unlocked"] is False
        assert portal_status["contract"]["is_legacy_import"] is True
        assert portal_status["contract"]["acceptance_source"] == "questionnaire_completed_date"
        assert portal_status["submissions"][0]["submission_source"] == "studio_ninja_questionnaire"

        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(ClientPortalToken)) == 0
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 0
            assert db.scalar(select(func.count()).select_from(ReminderLog)) == 0
            submission = db.scalar(select(FormSubmission))
            assert submission.submitted_at.date().isoformat() == "2025-03-15"

        assert client.post(f"/api/bookings/{booking_id}/portal", json={
            "expires_days": 365,
        }).status_code == 409
        assert client.post(f"/api/bookings/{booking_id}/quote/send", json={
            "expires_days": 365,
        }).status_code == 409
        assert client.delete(f"/api/payments/{invoice['payments'][0]['id']}").status_code == 409

        uploaded = client.post(
            f"/api/bookings/{booking_id}/documents?category=contract&source_system=studio_ninja"
            "&legacy_document_type=contract&legacy_reference=contract-2754576"
            "&document_date=2025-03-15&client_visible=true",
            files={"file": ("original-contract.pdf", b"%PDF-1.4 legacy", "application/pdf")},
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["is_client_visible"] is True
        assert client.delete(f"/api/documents/{uploaded.json()['id']}").status_code == 409

        assert client.post(f"/api/bookings/{booking_id}/automations", json={
            "enabled": True, "reason": "Migration checked", "confirmation": "ACTIVATE",
        }).status_code == 422
        activated = client.post(f"/api/bookings/{booking_id}/automations", json={
            "enabled": True, "reason": "Migration checked against source files",
            "confirmation": "ACTIVATE CLIENT EMAILS",
        })
        assert activated.status_code == 200
        assert activated.json()["automation_suppressed"] is False

        portal = client.post(f"/api/bookings/{booking_id}/portal", json={"expires_days": 365})
        assert portal.status_code == 201
        token = portal.json()["url"].split("/client/")[1]
        public = client.get(f"/api/client/{token}").json()
        assert public["documents"][0]["original_name"] == "original-contract.pdf"
        assert public["invoices"][0]["legacy_number"] == "WBM01706"
        assert public["contract"]["is_legacy_import"] is True
        assert client.post(f"/api/client/{token}/forms", json={
            "form_type": "final_questionnaire", "data": {"timeline": "Too early"},
        }).status_code == 409
        assert client.post(f"/api/bookings/{booking_id}/final-details", json={
            "unlocked": True, "reason": "Couple asked to complete early",
        }).status_code == 200
        assert client.post(f"/api/client/{token}/forms", json={
            "form_type": "final_questionnaire", "data": {"timeline": "Ceremony at 1pm"},
        }).status_code == 200

        assert client.post("/api/legacy-import/records", json=payload).status_code == 409

        digital = client.post("/api/bookings", json={
            "brand": "ivory", "kind": "digital", "status": "confirmed",
            "title": "Real Website", "client": {
                "first_name": "Alex", "last_name": "Smith", "email": "alex@example.com",
            }, "event_date": None, "venue_or_project": "Website",
            "quoted_total": 500, "deposit_amount": 0,
        })
        assert digital.status_code == 201
        ivory_invoice = client.post(f"/api/bookings/{digital.json()['id']}/invoices", json={
            "total": 500, "paid": 0, "issue_date": date.today().isoformat(),
        })
        assert ivory_invoice.status_code == 201
        assert ivory_invoice.json()["number"] == "ID02001"

        pdf = client.get(f"/api/invoices/{result['invoice_id']}/pdf")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")

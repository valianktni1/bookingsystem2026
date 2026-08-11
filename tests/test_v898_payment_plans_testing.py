from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, Invoice


TEST_ROOT = Path(__file__).parent


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)


def booking_payload(wedding_day):
    return {
        "brand": "wbm", "kind": "wedding", "status": "enquiry",
        "title": "Plan Test Couple",
        "client": {"first_name": "Alex", "last_name": "Test", "partner_name": "Sam Test",
                   "email": "real-couple@example.com", "phone": "07700 900111"},
        "event_date": wedding_day.isoformat(), "venue_or_project": "Test Hall",
        "venue_address": "Test Hall, Manchester", "quoted_total": 0, "deposit_amount": 0,
    }


def completed_form(wedding_day, plan):
    return {
        "primary_full_name": "Alex Test", "primary_phone": "07700 900111",
        "primary_email": "real-couple@example.com", "partner_full_name": "Sam Test",
        "partner_phone": "07700 900222", "partner_email": "sam@example.com",
        "street_address": "1 Test Road", "town": "Manchester", "county": "Greater Manchester",
        "postcode": "M1 1AA", "wedding_date": wedding_day.isoformat(), "ceremony_time": "13:00",
        "venue_name": "Test Hall", "venue_address": "Test Hall, Manchester",
        "ceremony_details": "Test Hall ceremony", "reception_details": "Test Hall reception",
        "package_selected": "Bronze Package 1 2026/27/28", "payment_plan": plan,
        "wedding_party_size": "8", "unique_events": "None", "guest_uploads": "Yes please",
        "additional_information": "", "highlight_music": "",
    }


def test_payment_plan_rebuilds_native_invoice_and_next_due_date():
    reset_database()
    wedding_day = date.today() + timedelta(days=240)
    with TestClient(app) as client:
        login(client)
        created = client.post("/api/bookings", json=booking_payload(wedding_day)).json()
        portal = client.post(f"/api/bookings/{created['id']}/portal", json={"expires_days":365}).json()
        token = portal["url"].split("/client/")[1]
        public = client.get(f"/api/client/{token}").json()
        bronze = next(item for item in public["catalog"]["packages"] if item["code"] == "bronze")
        accepted = client.post(f"/api/client/{token}/quote", json={
            "package_id": bronze["id"], "addon_ids": [], "confirmed": True,
        })
        assert accepted.status_code == 201
        invoice_id = accepted.json()["invoice"]["id"]

        saved = client.post(f"/api/client/{token}/forms", json={
            "form_type": "booking_form", "data": completed_form(wedding_day, "split"),
        })
        assert saved.status_code == 200
        record = client.get(f"/api/bookings/{created['id']}").json()
        invoice = next(item for item in record["invoices"] if item["id"] == invoice_id)
        assert [row["key"] for row in invoice["payment_schedule"]] == [
            "booking_fee", "instalment_90", "final_45",
        ]
        assert invoice["payment_schedule"][0]["amount"] == 100
        assert sum(row["amount"] for row in invoice["payment_schedule"]) == invoice["total"]
        assert invoice["payment_due_date"] == invoice["deposit_due_date"]
        assert invoice["final_due_date"] == (wedding_day - timedelta(days=45)).isoformat()

        first = client.post(f"/api/invoices/{invoice_id}/payments", json={
            "amount": 100, "paid_date": date.today().isoformat(), "payment_type": "bank_transfer",
        })
        assert first.status_code == 201
        assert first.json()["payment_schedule"][0]["status"] == "paid"
        assert first.json()["payment_due_date"] == (wedding_day - timedelta(days=90)).isoformat()

        changed = client.post(f"/api/client/{token}/forms", json={
            "form_type": "booking_form", "data": completed_form(wedding_day, "quarter"),
        })
        assert changed.status_code == 200
        with SessionLocal() as db:
            invoice = db.get(Invoice, invoice_id)
            assert invoice.legacy_source is None
            assert invoice.payment_schedule[0]["amount"] == 118.75
            assert invoice.payment_schedule[1]["amount"] == 356.25


def test_testing_mode_marks_records_routes_email_and_allows_test_cleanup(monkeypatch):
    reset_database()
    sent_to = []

    def fake_send(booking, profile, template, portal_url=None, extra_values=None,
                  recipient=None, reply_to=None):
        sent_to.append(recipient or booking.client.email)
        return template.subject, template.body

    monkeypatch.setattr("app.main.smtp_ready", lambda brand=None: True)
    monkeypatch.setattr("app.main.send_template_email", fake_send)
    with TestClient(app) as client:
        login(client)
        mode = client.put("/api/testing-mode", json={
            "enabled": True, "email": "safe-test@example.com",
        })
        assert mode.status_code == 200
        wedding_day = date.today() + timedelta(days=220)
        enquiry = client.post("/api/public/enquiries", json={
            "primary_first_name": "Real", "partner_first_name": "Address",
            "email": "must-not-receive@example.com", "phone": "07700 900333",
            "event_date": wedding_day.isoformat(), "location": "Test Hall",
            "package_interest": "Bronze", "selfie_booth_interest": "No thank you",
            "message": "Testing", "promo_code": "", "heard_about_us": "Google search",
            "fun_answer": "Beans", "privacy_agreed": True, "custom_answers": {},
        })
        assert enquiry.status_code == 201
        assert "safe-test@example.com" in sent_to
        assert "must-not-receive@example.com" not in sent_to
        with SessionLocal() as db:
            booking = db.scalar(select(Booking).where(Booking.title == "Real & Address"))
            booking_id = booking.id
            assert booking.is_test is True
            assert booking.workflow_state["test_email"] == "safe-test@example.com"

        # Turning global testing off does not remove the permanent safety lock from this test record.
        assert client.put("/api/testing-mode", json={
            "enabled": False, "email": "safe-test@example.com",
        }).status_code == 200
        record = client.get(f"/api/bookings/{booking_id}").json()
        assert record["is_test"] is True

        invoice = client.post(f"/api/bookings/{booking_id}/invoices", json={
            "total": 10, "paid": 0, "issue_date": date.today().isoformat(),
            "description": "Test invoice",
        }).json()
        assert client.post(f"/api/invoices/{invoice['id']}/payments", json={
            "amount": 10, "paid_date": date.today().isoformat(), "payment_type": "bank_transfer",
        }).status_code == 201
        removed = client.post(f"/api/bookings/{booking_id}/permanent-delete", json={
            "reason": "Completed safe end-to-end test", "confirmation": "DELETE Real & Address",
        })
        assert removed.status_code == 200

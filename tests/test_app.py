import os
import importlib
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
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.email_service import build_email_message
from app.main import app
from app.models import (Booking, Brand, BusinessProfile, Client, ContractAcceptance,
                        ReminderLog, Task)


def booking_payload(brand="wbm", title="Sophie & James"):
    return {
        "brand": brand,
        "kind": "wedding" if brand == "wbm" else "digital",
        "status": "confirmed",
        "title": title,
        "client": {
            "first_name": "Sophie" if brand == "wbm" else "Chris",
            "last_name": "Taylor",
            "partner_name": "James" if brand == "wbm" else None,
            "company_name": None if brand == "wbm" else title,
            "email": f"{brand}@example.com",
        },
        "event_date": "2026-10-04",
        "venue_or_project": "Peckforton Castle" if brand == "wbm" else "Website rebuild",
        "venue_address": "Peckforton Castle, Tarporley CW6 9TN" if brand == "wbm" else None,
        "venue_place_id": "test-place-peckforton" if brand == "wbm" else None,
        "venue_lat": 53.117 if brand == "wbm" else None,
        "venue_lng": -2.698 if brand == "wbm" else None,
        "package_name": "Platinum" if brand == "wbm" else "Website + CMS",
        "quoted_total": 1299 if brand == "wbm" else 399,
        "deposit_amount": 300 if brand == "wbm" else 0,
        "deposit_paid_date": "2026-01-18" if brand == "wbm" else None,
    }


def test_branded_email_artwork_is_brand_specific():
    wedding = Booking(brand=Brand.WBM, title="Sophie & James")
    wedding.client = Client(first_name="Sophie", last_name="Taylor", email="sophie@example.com")
    wbm_profile = BusinessProfile(brand=Brand.WBM, display_name="Weddings By Mark",
                                  invoice_prefix="WBM", email="mark@perfectweddingsbymark.uk",
                                  phone="07712 117357", website="perfectweddingsbymark.uk")
    wbm_message = build_email_message(wedding, wbm_profile, "Your quote",
                                      "Hi Sophie\n\nOpen https://booking.weddingsbymark.uk/client/example",
                                      "mark@perfectweddingsbymark.uk")
    wbm_html = next(part.get_content() for part in wbm_message.walk()
                    if part.get_content_type() == "text/html")
    wbm_images = {part.get_filename() for part in wbm_message.walk()
                  if part.get_content_maintype() == "image"}
    assert "cid:weddings-by-mark-logo" in wbm_html
    assert "cid:weddings-by-mark-awards" in wbm_html
    assert ">OPEN YOUR SECURE ACCOUNT</a>" in wbm_html
    assert ">https://booking.weddingsbymark.uk/client/example</a>" not in wbm_html
    assert wbm_images == {"weddings-by-mark-logo.png", "weddings-by-mark-awards.png"}
    notification = build_email_message(
        wedding, wbm_profile, "New enquiry", "A new enquiry has arrived",
        "mark@perfectweddingsbymark.uk", recipient="mark@perfectweddingsbymark.uk",
        reply_to="sophie@example.com",
    )
    assert notification["To"] == "mark@perfectweddingsbymark.uk"
    assert notification["Reply-To"] == "sophie@example.com"

    project = Booking(brand=Brand.IVORY, title="Broadfield Motors")
    project.client = Client(first_name="Chris", last_name="Taylor", email="chris@example.com")
    ivory_profile = BusinessProfile(brand=Brand.IVORY, display_name="Ivory Digital",
                                    invoice_prefix="ID", email="admin@ivorydigital.uk",
                                    phone="07712 117357", website="ivorydigital.uk")
    ivory_message = build_email_message(project, ivory_profile, "Your project", "Hi Chris",
                                        "admin@ivorydigital.uk")
    ivory_html = next(part.get_content() for part in ivory_message.walk()
                      if part.get_content_type() == "text/html")
    ivory_images = {part.get_filename() for part in ivory_message.walk()
                    if part.get_content_maintype() == "image"}
    assert "cid:ivory-digital-logo" in ivory_html
    assert "weddings-by-mark-awards" not in ivory_html
    assert ivory_images == {"ivory-digital-logo.png"}


def test_deleted_default_email_template_stays_deleted_after_restart():
    db_file = TEST_ROOT / "test.db"
    engine.dispose()
    db_file.unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        rows = client.get("/api/communications/templates").json()["templates"]
        deleted = next(row for row in rows
                       if row["brand"] == "wbm" and row["template_key"] == "contract_reminder")
        assert client.delete(f"/api/communications/templates/{deleted['id']}").status_code == 204

    # Startup must not quietly restore a template Mark deliberately removed.
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        keys = {(row["brand"], row["template_key"])
                for row in client.get("/api/communications/templates").json()["templates"]}
        assert ("wbm", "contract_reminder") not in keys


def test_short_wbm_contract_is_upgraded_to_complete_rev_1_4_on_restart():
    db_file = TEST_ROOT / "test.db"
    engine.dispose()
    db_file.unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        contracts = client.get("/api/communications/templates").json()["contracts"]
        wedding_contract = next(row for row in contracts if row["brand"] == "wbm")
        assert client.patch(
            f"/api/communications/contracts/{wedding_contract['id']}",
            json={"version": "Rev 1.3 - August 2022", "body": "Short former contract"},
        ).status_code == 200

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        contracts = client.get("/api/communications/templates").json()["contracts"]
        wedding_contract = next(row for row in contracts if row["brand"] == "wbm")
        assert wedding_contract["version"] == "Rev 1.4 - August 2026"
        assert len(wedding_contract["body"].split()) > 2500
        assert "m) DRONE COVERAGE" in wedding_contract["body"]


def test_zero_payment_voided_test_booking_can_be_deleted_without_reusing_number():
    db_file = TEST_ROOT / "test.db"
    engine.dispose()
    db_file.unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)
    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200
        booking = client.post("/api/bookings", json=booking_payload(title="Test Couple")).json()
        first_invoice = client.post(f"/api/bookings/{booking['id']}/invoices", json={
            "total": 899, "paid": 0, "issue_date": "2026-08-06",
            "due_date": "2026-08-20", "description": "Test quote invoice",
        })
        assert first_invoice.status_code == 201
        first_number = first_invoice.json()["number"]
        assert client.post(f"/api/invoices/{first_invoice.json()['id']}/void", json={
            "reason": "Test quote created while checking the workflow",
        }).status_code == 200
        retained_invoice = next(
            item for item in client.get(f"/api/bookings/{booking['id']}").json()["invoices"]
            if item["id"] == first_invoice.json()["id"]
        )
        assert retained_invoice["status"] == "void"
        assert retained_invoice["void_record"]["reason"] == (
            "Test quote created while checking the workflow"
        )
        assert retained_invoice["void_record"]["voided_by"] == "mark@example.com"
        assert retained_invoice["void_record"]["voided_at"]
        register_invoice = next(
            item for item in client.get("/api/invoices").json()
            if item["id"] == first_invoice.json()["id"]
        )
        assert register_invoice["void_record"] == retained_invoice["void_record"]
        assert "Test quote created while checking the workflow" in retained_invoice["notes"]
        deleted = client.post(f"/api/bookings/{booking['id']}/permanent-delete", json={
            "reason": "Remove completed test enquiry and booking",
            "confirmation": "DELETE Test Couple",
        })
        assert deleted.status_code == 200
        assert client.get(f"/api/bookings/{booking['id']}").status_code == 404

        next_booking = client.post("/api/bookings", json=booking_payload(title="Real Couple")).json()
        next_invoice = client.post(f"/api/bookings/{next_booking['id']}/invoices", json={
            "total": 899, "paid": 0, "issue_date": "2026-08-06",
            "due_date": "2026-08-20", "description": "Real invoice",
        })
        assert next_invoice.status_code == 201
        assert int(next_invoice.json()["number"].replace("WBM", "")) == int(first_number.replace("WBM", "")) + 1
        assert client.post(f"/api/invoices/{next_invoice.json()['id']}/payments", json={
            "amount": 100, "paid_date": "2026-08-06", "payment_type": "bank_transfer",
        }).status_code == 201
        protected = client.post(f"/api/bookings/{next_booking['id']}/permanent-delete", json={
            "reason": "This must be refused because real money is recorded",
            "confirmation": "DELETE Real Couple",
        })
        assert protected.status_code == 409


def test_phase_two_b_flow(monkeypatch):
    db_file = TEST_ROOT / "test.db"
    engine.dispose()
    db_file.unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "phase": "2B", "smtp_configured": False,
                                 "reminders_enabled": False, "maps_configured": False,
                                 "imap_configured": False,
                                 "accounts_integration_enabled": False,
                                 "accounts_auto_sync": False,
                                 "google_calendar_configured": False,
                                     "build": "2026.08.22-dashboard-timings-email-v8.24"}
        assert client.get("/api/public/config").json() == {
            "google_maps_api_key": None, "google_maps_enabled": False,
        }

        homepage = client.get("/")
        assert homepage.status_code == 200
        assert "Mark's Business Studio" in homepage.text
        admin_javascript = client.get("/static/app.js").text
        assert 'id="record-inline-back"' in admin_javascript
        email_centre_javascript = client.get("/static/v895.js").text
        assert 'id="record-email-client-top"' in email_centre_javascript
        assert "Email client" in email_centre_javascript
        assert "function renderQuestionnaires" in admin_javascript
        compatibility_javascript = client.get("/static/v82.js").text
        assert "Change final payment date" in compatibility_javascript
        assert "data-due-invoice" in compatibility_javascript
        assert "changeInvoiceDueDate" in compatibility_javascript
        workspace_javascript = client.get("/static/v895.js").text
        assert "record-command-header" in workspace_javascript
        assert "Quote & emails" in workspace_javascript
        assert "Forms & agreement" in workspace_javascript
        assert "record-primary-actions" in workspace_javascript
        client_javascript = client.get("/static/client.js").text
        assert 'name:"Final details"' not in client_javascript
        assert 'submitForm(event,"final_questionnaire")' not in client_javascript

        assert client.get("/api/dashboard").status_code == 401

        login = client.post("/api/auth/login", json={"email": "mark@example.com", "password": "SecureTestPassword!123"})
        assert login.status_code == 200

        wedding = client.post("/api/bookings", json=booking_payload())
        assert wedding.status_code == 201
        wedding_data = wedding.json()
        assert wedding_data["brand"] == "wbm"
        assert wedding_data["venue_place_id"] == "test-place-peckforton"
        assert wedding_data["venue_address"].startswith("Peckforton Castle")
        assert len(wedding_data["tasks"]) == 4
        assert {task["workflow_key"] for task in wedding_data["tasks"]} == {
            "wbm_quote", "wbm_booking_form", "wbm_contract", "wbm_final_details_call",
        }
        final_call = next(task for task in wedding_data["tasks"]
                          if task["workflow_key"] == "wbm_final_details_call")
        assert final_call["title"] == "Finalise wedding details by phone"
        assert final_call["due_at"].startswith("2026-09-04T10:00:00")

        templates = client.get("/api/communications/templates")
        assert templates.status_code == 200
        assert len(templates.json()["templates"]) >= 10
        assert len(templates.json()["contracts"]) == 2
        assert templates.json()["smtp_by_brand"] == {
            "wbm": {"configured": False, "username": "mark@perfectweddingsbymark.uk"},
            "ivory": {"configured": False, "username": "admin@ivorydigital.uk"},
        }
        wedding_contract = next(row for row in templates.json()["contracts"] if row["brand"] == "wbm")
        assert wedding_contract["title"] == "Weddings By Mark Contract"
        assert wedding_contract["version"] == "Rev 1.4 - August 2026"
        assert len(wedding_contract["body"].split()) > 2500
        assert "m) DRONE COVERAGE" in wedding_contract["body"]
        assert "15. TIME FRAMES" in wedding_contract["body"]
        assert "guest QR-code uploads" in wedding_contract["body"]
        quote_template = next(row for row in templates.json()["templates"]
                              if row["brand"] == "wbm" and row["template_key"] == "quote")
        assert "planning a wedding can feel overwhelming" in quote_template["body"]
        assert "[VIEW YOUR FULL QUOTE HERE]({portal_url})" in quote_template["body"]
        assert "{bank_account_name}" in quote_template["body"]
        reminder_keys = {row["template_key"] for row in templates.json()["templates"]
                         if row["brand"] == "wbm" and row["is_active"]}
        assert {"quote_followup_1", "quote_followup_final", "deposit_due_1", "check_in_120",
                "balance_due_7", "balance_due_1", "balance_overdue_2"} <= reminder_keys
        assert not {"balance_due_14", "balance_due_10"} & reminder_keys
        admin_enquiry_template = next(row for row in templates.json()["templates"]
                                      if row["brand"] == "wbm"
                                      and row["template_key"] == "new_enquiry_admin")
        assert "New wedding enquiry" in admin_enquiry_template["subject"]
        enquiry_template = next(row for row in templates.json()["templates"]
                                if row["brand"] == "wbm"
                                and row["template_key"] == "enquiry_received")
        assert "{portal_url}" in enquiry_template["body"]
        accepted_template = next(row for row in templates.json()["templates"]
                                 if row["brand"] == "wbm"
                                 and row["template_key"] == "quote_accepted")
        assert "Wedding Booking Form/questionnaire" in accepted_template["body"]
        assert "digitally sign your wedding contract" in accepted_template["body"]
        payment_template = next(row for row in templates.json()["templates"]
                                if row["brand"] == "wbm"
                                and row["template_key"] == "payment_received")
        assert {"{payment_amount}", "{total_paid}", "{outstanding_balance}",
                "{portal_url}"} <= {item for item in (
                    "{payment_amount}", "{total_paid}", "{outstanding_balance}",
                    "{portal_url}") if item in payment_template["body"]}
        preview = client.get(f"/api/communications/templates/{quote_template['id']}/preview")
        assert preview.status_code == 200
        assert "/static/branding/weddings-by-mark-logo.png" in preview.json()["html"]
        assert ">VIEW YOUR FULL QUOTE HERE</a>" in preview.json()["html"]
        assert ">https://booking.weddingsbymark.uk/client/example-preview-link</a>" not in preview.json()["html"]
        assert preview.json()["test_recipient"] == "mark@perfectweddingsbymark.uk"
        custom_template = client.post("/api/communications/templates", json={
            "brand": "wbm", "template_key": "custom_client_note",
            "display_name": "Custom client note",
            "subject": "Hello {client_first_name}",
            "body": "Hi {client_first_name},\n\nThis deliberately has no link placeholder.",
            "is_active": True,
        })
        assert custom_template.status_code == 201
        custom_preview = client.get(
            f"/api/communications/templates/{custom_template.json()['id']}/preview"
        )
        assert custom_preview.status_code == 200
        assert "VIEW YOUR WEDDING ACCOUNT, INVOICES AND BOOKING DETAILS" in custom_preview.json()["body"]
        assert "/client/example-preview-link" in custom_preview.json()["body"]
        assert client.patch(
            f"/api/communications/templates/{custom_template.json()['id']}",
            json={"is_active": False, "display_name": "Custom note paused"},
        ).status_code == 200
        assert client.delete(
            f"/api/communications/templates/{custom_template.json()['id']}"
        ).status_code == 204

        portal = client.post(f"/api/bookings/{wedding_data['id']}/portal", json={"expires_days": 90})
        assert portal.status_code == 201
        token = portal.json()["url"].split("/client/")[1]
        public_data = client.get(f"/api/client/{token}")
        assert public_data.status_code == 200
        assert public_data.json()["record"]["title"] == "Sophie & James"
        prepared_quote = client.post(f"/api/bookings/{wedding_data['id']}/quote/send",
                                     json={"expires_days": 90})
        assert prepared_quote.status_code == 200
        assert prepared_quote.json()["url"].endswith("?tab=quote")
        assert prepared_quote.json()["email_sent"] is False
        direct_quote_token = prepared_quote.json()["url"].split("/client/")[1].split("?")[0]
        assert client.get(f"/api/client/{direct_quote_token}").status_code == 200
        form = client.post(f"/api/client/{token}/forms", json={
            "form_type": "booking_form", "data": {
                    "primary_full_name": "Sophie Taylor", "primary_phone": "07700 900123",
                    "primary_email": "sophie@example.com",
                "partner_full_name": "James Taylor", "street_address": "1 Test Road",
                "town": "Knutsford", "county": "Cheshire", "postcode": "WA16 0AA",
                    "wedding_date": "2026-10-04", "ceremony_time": "13:00",
                    "ceremony_details": "Peckforton Castle ceremony",
                    "reception_details": "Peckforton Castle reception",
                    "package_selected": "Platinum Package 4 2026/27/28",
                    "payment_plan": "standard", "wedding_party_size": "8",
                    "unique_events": "None",
            }
        })
        assert form.status_code == 200
        with SessionLocal() as db:
            booking_form_review = db.scalar(select(Task).where(
                Task.booking_id == wedding_data["id"],
                Task.workflow_key == "wbm_review_booking_form",
            ))
            assert booking_form_review is not None and booking_form_review.completed is False
        accepted = client.post(f"/api/client/{token}/contract", json={
            "accepted_name": "Sophie Taylor", "accepted_email": "wbm@example.com", "agreed": True
        })
        assert accepted.status_code == 200
        portal_status = client.get(f"/api/bookings/{wedding_data['id']}/portal").json()
        assert portal_status["contract"]["accepted_name"] == "Sophie Taylor"
        assert portal_status["contract"]["version"] == "Rev 1.4 - August 2026"
        assert portal_status["contract"]["supplier_signed_name"] == "Mark Adam Powell"
        assert portal_status["submissions"][0]["form_type"] == "booking_form"
        assert portal_status["submissions"][0]["data"]["ceremony_time"] == "13:00"
        # Editing the live template must never rewrite the signed agreement snapshot.
        assert client.patch(
            f"/api/communications/contracts/{wedding_contract['id']}",
            json={"body": "A later live-template edit"},
        ).status_code == 200
        with SessionLocal() as db:
            signed_snapshot = db.scalar(select(ContractAcceptance).where(
                ContractAcceptance.booking_id == wedding_data["id"]
            ))
            assert signed_snapshot.contract_version == "Rev 1.4 - August 2026"
            assert "m) DRONE COVERAGE" in signed_snapshot.contract_body
            assert signed_snapshot.contract_body != "A later live-template edit"
        assert client.patch(
            f"/api/communications/contracts/{wedding_contract['id']}",
            json={"body": wedding_contract["body"]},
        ).status_code == 200
        assert client.post(f"/api/client/{token}/contract", json={
            "accepted_name": "Sophie Taylor", "accepted_email": "wbm@example.com", "agreed": True
        }).status_code == 409
        assert client.post(f"/api/bookings/{wedding_data['id']}/emails/send",
                           json={"template_key": "booking_link", "portal_url": portal.json()["url"]}).status_code == 503

        digital = client.post("/api/bookings", json=booking_payload("ivory", "Broadfield Motors"))
        assert digital.status_code == 201
        digital_data = digital.json()
        assert digital_data["kind"] == "digital"
        assert len(digital_data["tasks"]) == 7

        edited = client.patch(f"/api/bookings/{wedding_data['id']}", json={
            "status": "in_progress",
            "package_name": "Platinum Plus",
            "client": {"phone": "07700 900123", "address": "Manchester"},
        })
        assert edited.status_code == 200
        assert edited.json()["status"] == "in_progress"
        assert edited.json()["client"]["phone"] == "07700 900123"
        assert edited.json()["package_name"] == "Platinum Plus"

        note = client.post(f"/api/bookings/{wedding_data['id']}/notes", json={"body": "Couple requested sunset portraits."})
        assert note.status_code == 201
        assert client.get(f"/api/bookings/{wedding_data['id']}").json()["booking_notes"][0]["body"].startswith("Couple")

        wbm_invoice = client.post(f"/api/bookings/{wedding_data['id']}/invoices", json={"total": 1299, "paid": 300, "issue_date": "2026-01-18"})
        assert wbm_invoice.status_code == 201
        assert wbm_invoice.json()["number"] == "WBM02001"
        assert wbm_invoice.json()["status"] == "part_paid"
        assert wbm_invoice.json()["payments"][0]["amount"] == 300

        assert client.patch(f"/api/bookings/{digital_data['id']}", json={"status": "enquiry"}).status_code == 200
        ivory_invoice = client.post(f"/api/bookings/{digital_data['id']}/invoices", json={"total": 399, "paid": 399, "issue_date": "2026-01-19"})
        assert ivory_invoice.status_code == 201
        assert ivory_invoice.json()["number"] == "ID02001"
        assert ivory_invoice.json()["status"] == "paid"
        assert client.get(f"/api/bookings/{digital_data['id']}").json()["status"] == "confirmed"

        payment = client.post(f"/api/invoices/{wbm_invoice.json()['id']}/payments", json={
            "amount": 999, "paid_date": "2026-08-03", "payment_type": "cash",
            "reference": "WBM02001"
        })
        assert payment.status_code == 201
        assert payment.json()["status"] == "paid"
        assert payment.json()["balance"] == 0
        refreshed_wedding = client.get(f"/api/bookings/{wedding_data['id']}").json()
        assert any(
            row["payment_type"] == "cash"
            for invoice in refreshed_wedding["invoices"]
            for row in invoice["payments"]
        )

        pdf = client.get(f"/api/invoices/{wbm_invoice.json()['id']}/pdf")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")
        receipt = client.get(f"/api/invoices/{wbm_invoice.json()['id']}/receipt.pdf")
        assert receipt.status_code == 200

        invoices = client.get("/api/invoices").json()
        assert {row["number"] for row in invoices} == {"ID02001", "WBM02001"}

        catalog = client.get("/api/catalog?brand=wbm").json()
        assert [row["price"] for row in catalog["packages"]] == [475, 699, 899, 1299, 1699]
        temporary_package = client.post("/api/catalog/packages?brand=wbm", json={
            "code": "duplicate_test", "name": "Duplicate test package",
            "description": "Safe temporary package", "price": 1,
            "deposit_amount": 0, "display_order": 99, "is_active": True,
        })
        assert temporary_package.status_code == 201
        assert client.delete(
            f"/api/catalog/packages/{temporary_package.json()['id']}"
        ).status_code == 204
        temporary_addon = client.post("/api/catalog/addons?brand=wbm", json={
            "code": "duplicate_extra", "name": "Duplicate test extra",
            "description": "Safe temporary add-on", "price": 1,
            "eligible_package_codes": ["gold"], "display_order": 99, "is_active": True,
        })
        assert temporary_addon.status_code == 201
        assert client.delete(
            f"/api/catalog/addons/{temporary_addon.json()['id']}"
        ).status_code == 204
        refreshed_catalog = client.get("/api/catalog?brand=wbm&include_inactive=true").json()
        assert not any(row["code"] == "duplicate_test" for row in refreshed_catalog["packages"])
        assert not any(row["code"] == "duplicate_extra" for row in refreshed_catalog["addons"])
        album = next(row for row in catalog["addons"] if row["code"] == "album_offer")
        speeches = next(row for row in catalog["addons"] if row["code"] == "speeches")
        travel = client.post("/api/catalog/addons?brand=wbm", json={
            "code": "travel_expenses", "name": "Travel expenses",
            "description": "Travel expenses agreed for this wedding", "price": 50,
            "eligible_package_codes": [], "display_order": 90, "is_active": True,
        }).json()
        discount = client.post("/api/catalog/addons?brand=wbm", json={
            "code": "thank_you_25", "name": "THANKYOU25 discount",
            "description": "Discount code applied by Mark", "price": 25,
            "eligible_package_codes": [], "display_order": 91, "is_active": True,
            "is_discount": True,
        }).json()
        preparation = client.put(f"/api/bookings/{wedding_data['id']}/quote/preparation", json={
            "required_addons": [{"addon_id": travel["id"], "price": 75}],
            "discounts": [{"addon_id": discount["id"], "price": 25}],
        })
        assert preparation.status_code == 200
        assert preparation.json()["required_addons"][0]["price"] == 75
        prepared_public = client.get(f"/api/client/{token}").json()
        assert prepared_public["quote_preparation"]["discounts"][0]["name"] == "THANKYOU25 discount"
        assert not any(item["id"] == discount["id"] for item in prepared_public["catalog"]["addons"])
        assert album["price"] == 120
        gold = next(row for row in catalog["packages"] if row["code"] == "gold")
        assert client.post(f"/api/client/{token}/quote", json={
            "package_id": gold["id"], "addon_ids": [speeches["id"]], "confirmed": True
        }).status_code == 422
        quote = client.post(f"/api/client/{token}/quote", json={
            "package_id": gold["id"], "addon_ids": [album["id"]], "confirmed": True
        })
        assert quote.status_code == 201
        assert client.delete(f"/api/catalog/packages/{gold['id']}").status_code == 409
        assert client.delete(f"/api/catalog/addons/{album['id']}").status_code == 409
        assert quote.json()["quote"]["total"] == 1069
        assert quote.json()["invoice"]["number"] == "WBM02002"
        assert quote.json()["acceptance_email_sent"] is False
        assert quote.json()["google_calendar"]["status"] == "pending"
        assert quote.json()["google_calendar"]["desired_action"] == "create"
        expected_deposit_due = date.today() + timedelta(days=1)
        expected_balance_due = max(date(2026, 10, 4) - timedelta(days=45), expected_deposit_due)
        assert quote.json()["invoice"]["deposit_due_date"] == expected_deposit_due.isoformat()
        assert quote.json()["invoice"]["due_date"] == expected_balance_due.isoformat()
        assert [line["name"] for line in quote.json()["invoice"]["line_items"]] == [
            "Gold Package 3 2026/27/28", "Travel expenses", "Wedding album offer",
            "THANKYOU25 discount"
        ]
        assert quote.json()["invoice"]["line_items"][1]["required"] is True
        assert quote.json()["invoice"]["line_items"][-1]["total"] == -25
        assert client.put(f"/api/bookings/{wedding_data['id']}/quote/preparation", json={
            "required_addons": [], "discounts": []
        }).status_code == 409
        assert "Highlight Video" in quote.json()["invoice"]["line_items"][0]["description"]
        refreshed_public = client.get(f"/api/client/{token}").json()
        assert refreshed_public["quote"]["invoice_number"] == "WBM02002"
        assert refreshed_public["record"]["quoted_total"] == 1069
        assert refreshed_public["invoices"][0]["number"] == "WBM02002"
        assert refreshed_public["invoices"][0]["payment_due_date"] == expected_deposit_due.isoformat()
        assert refreshed_public["invoices"][0]["wedding_date"] == "2026-10-04"
        assert refreshed_public["invoices"][0]["deposit_due_date"] == expected_deposit_due.isoformat()
        ordered_invoices = client.get("/api/invoices").json()
        assert ordered_invoices[0]["number"] == "WBM02002"
        assert ordered_invoices[0]["payment_due_date"] == expected_deposit_due.isoformat()
        assert all(row["balance"] == 0 for row in ordered_invoices[1:])
        assert client.get(f"/api/bookings/{wedding_data['id']}").json()["balance_due_date"] == expected_balance_due.isoformat()
        public_invoice_pdf = client.get(
            f"/api/client/{token}/invoices/{quote.json()['invoice']['id']}/invoice.pdf"
        )
        assert public_invoice_pdf.status_code == 200
        assert public_invoice_pdf.content.startswith(b"%PDF")
        digital_portal = client.post(f"/api/bookings/{digital_data['id']}/portal",
                                     json={"expires_days": 90}).json()
        digital_token = digital_portal["url"].split("/client/")[1]
        assert client.get(
            f"/api/client/{digital_token}/invoices/{quote.json()['invoice']['id']}/invoice.pdf"
        ).status_code == 404
        assert client.get(
            f"/api/client/{token}/invoices/{quote.json()['invoice']['id']}/receipt.pdf"
        ).status_code == 422
        quote_pdf = client.get(f"/api/invoices/{quote.json()['invoice']['id']}/pdf")
        assert quote_pdf.status_code == 200
        assert quote_pdf.content.startswith(b"%PDF")
        assert client.post(f"/api/client/{token}/quote", json={
            "package_id": gold["id"], "addon_ids": [], "confirmed": True
        }).status_code == 409

        # Keep the balance-reminder assertions independent of the real date on
        # which the suite runs. Otherwise the one-day booking-fee reminder can
        # legitimately fall on the same day as the seven-day balance reminder.
        assert client.post(f"/api/invoices/{quote.json()['invoice']['id']}/payments", json={
            "amount": quote.json()["invoice"]["deposit_amount"],
            "paid_date": date.today().isoformat(), "payment_type": "bank_transfer",
        }).status_code == 201

        main_module = importlib.import_module("app.main")
        with monkeypatch.context() as reminder_patch:
            class FrozenDate(date):
                current = expected_balance_due

                @classmethod
                def today(cls):
                    return cls.current

            reminder_patch.setattr(main_module, "date", FrozenDate)
            reminder_patch.setattr(
                main_module, "send_template_email",
                lambda booking, profile, template, portal_url=None: (template.subject, template.body),
            )
            schedule = [
                (expected_balance_due - timedelta(days=7), "balance_due_7"),
                (expected_balance_due - timedelta(days=1), "balance_due_1"),
                (expected_balance_due + timedelta(days=2), "balance_overdue_2"),
                (expected_balance_due + timedelta(days=4), "balance_overdue_4"),
            ]
            for reminder_day, reminder_key in schedule:
                FrozenDate.current = reminder_day
                with SessionLocal() as db:
                    result = main_module.run_due_reminders(db)
                    assert result == {"sent": 1, "skipped": 0, "failed": 0}
                    saved_reminder = db.scalar(select(ReminderLog).where(
                        ReminderLog.booking_id == wedding_data["id"],
                        ReminderLog.reminder_key == reminder_key,
                    ))
                    assert saved_reminder and saved_reminder.status == "sent"
            with SessionLocal() as db:
                paid_invoice = db.get(main_module.Invoice, quote.json()["invoice"]["id"])
                paid_invoice.paid = paid_invoice.total
                paid_invoice.status = "paid"
                db.commit()
                FrozenDate.current = expected_balance_due - timedelta(days=7)
                assert main_module.run_due_reminders(db) == {"sent": 0, "skipped": 0, "failed": 0}
                paid_invoice.paid = 0
                paid_invoice.status = "unpaid"
                db.commit()

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["confirmed"] == 1
        # The submitted Wedding Booking Form now remains as one private review
        # item until Mark deliberately marks it reviewed.
        assert dashboard.json()["open_tasks"] == 9

        upload = client.post(
            f"/api/bookings/{wedding_data['id']}/documents?category=contract",
            files={"file": ("signed-contract.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert upload.status_code == 201
        assert upload.json()["category"] == "contract"

        task_id = wedding_data["tasks"][0]["id"]
        completed = client.patch(f"/api/tasks/{task_id}", json={"completed": True})
        assert completed.status_code == 200
        assert completed.json()["completed"] is True

        archived = client.post(f"/api/bookings/{digital_data['id']}/archive")
        assert archived.status_code == 200
        assert len(client.get("/api/bookings").json()) == 1
        assert len(client.get("/api/bookings?archived=true").json()) == 1
        assert client.post(f"/api/bookings/{digital_data['id']}/restore").status_code == 200

        businesses = client.get("/api/businesses").json()
        assert len(businesses) == 2
        assert next(row for row in businesses if row["brand"] == "ivory")["email"] == "admin@ivorydigital.uk"
        saved = client.patch("/api/businesses/wbm", json={"bank_details": {
            "account_name": "Mark Adam Powell", "sort_code": "04-06-05", "account_number": "12345678"
        }})
        assert saved.status_code == 200

        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/bookings").status_code == 401

        enquiry_page = client.get("/enquiry")
        assert enquiry_page.status_code == 200
        assert 'id="enquiry-fields"' in enquiry_page.text
        public_form = client.get("/api/public/enquiry-form")
        assert public_form.status_code == 200
        assert "let the countdown to your best day ever begin" in public_form.json()["heading"]
        assert client.get("/api/public/catalog").status_code == 200
        enquiry_payload = {
            "primary_first_name": "Rachel", "partner_first_name": "Thomas",
            "email": "rachel@example.com", "phone": "07700 900456",
            "event_date": "2027-06-12", "location": "Lytham Hall",
            "venue_address": "Lytham Hall, Ballam Road, Lytham St Annes FY8 4JX",
            "venue_place_id": "test-place-lytham-hall",
            "venue_lat": 53.749, "venue_lng": -2.978,
            "package_interest": "Gold Package 3 2026/27/28",
            "selfie_booth_interest": "maybe", "message": "Relaxed summer wedding",
            "promo_code": None, "heard_about_us": "Google search",
            "fun_answer": "Beans on toast", "privacy_agreed": True, "website": None,
        }
        sent_enquiry_emails = []

        def fake_enquiry_email(booking, profile, template, portal_url=None, extra_values=None,
                               recipient=None, reply_to=None):
            sent_enquiry_emails.append({
                "key": template.template_key,
                "recipient": recipient or booking.client.email,
                "reply_to": reply_to,
                "portal_url": portal_url,
                "values": extra_values or {},
            })
            return template.subject, template.body

        main_module = importlib.import_module("app.main")
        with monkeypatch.context() as enquiry_patch:
            enquiry_patch.setattr(main_module, "smtp_ready", lambda brand=None: True)
            enquiry_patch.setattr(main_module, "send_template_email", fake_enquiry_email)
            enquiry = client.post("/api/public/enquiries", json=enquiry_payload)
        assert enquiry.status_code == 201
        assert enquiry.json()["ok"] is True
        assert enquiry.json()["portal_created"] is True
        assert [mail["key"] for mail in sent_enquiry_emails] == [
            "enquiry_received", "new_enquiry_admin"
        ]
        assert sent_enquiry_emails[0]["recipient"] == "rachel@example.com"
        enquiry_portal_url = sent_enquiry_emails[0]["portal_url"]
        assert "/client/" in enquiry_portal_url
        assert sent_enquiry_emails[1]["recipient"] == "mark@perfectweddingsbymark.uk"
        assert sent_enquiry_emails[1]["reply_to"] == "rachel@example.com"
        assert sent_enquiry_emails[1]["values"]["heard_about_us"] == "Google search"
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123"
        }).status_code == 200
        imported_enquiry = client.get("/api/bookings?q=Rachel").json()
        assert len(imported_enquiry) == 1
        assert imported_enquiry[0]["status"] == "enquiry"
        assert imported_enquiry[0]["venue_or_project"] == "Lytham Hall"
        assert imported_enquiry[0]["venue_place_id"] == "test-place-lytham-hall"
        assert imported_enquiry[0]["venue_address"].startswith("Lytham Hall")

        # Complete automated client journey: enquiry -> quote -> forms -> first
        # partial payment. A £50 first payment must secure a £100-deposit booking.
        enquiry_token = enquiry_portal_url.split("/client/")[1]
        enquiry_portal = client.get(f"/api/client/{enquiry_token}")
        assert enquiry_portal.status_code == 200
        assert enquiry_portal.json()["record"]["status"] == "enquiry"
        assert enquiry_portal.json()["quote"] is None
        assert client.post(f"/api/client/{enquiry_token}/forms", json={
            "form_type": "booking_form", "data": {"primary_full_name": "Rachel Green"}
        }).status_code == 409
        assert client.post(f"/api/client/{enquiry_token}/contract", json={
            "accepted_name": "Rachel Green", "accepted_email": "rachel@example.com",
            "agreed": True,
        }).status_code == 409

        journey_emails = []

        def fake_journey_email(booking, profile, template, portal_url=None, extra_values=None,
                               recipient=None, reply_to=None):
            journey_emails.append({
                "key": template.template_key,
                "portal_url": portal_url,
                "values": extra_values or {},
                "body": template.body,
            })
            return template.subject, template.body

        with monkeypatch.context() as journey_patch:
            journey_patch.setattr(main_module, "smtp_ready", lambda brand=None: True)
            journey_patch.setattr(main_module, "send_template_email", fake_journey_email)
            sent_quote = client.post(
                f"/api/bookings/{imported_enquiry[0]['id']}/quote/send",
                json={"expires_days": 365},
            )
            assert sent_quote.status_code == 200
            assert sent_quote.json()["email_sent"] is True
            quote_token = sent_quote.json()["url"].split("/client/")[1].split("?")[0]
            public_catalog = client.get("/api/public/catalog").json()
            bronze = next(row for row in public_catalog["packages"] if row["code"] == "bronze")
            accepted_quote = client.post(f"/api/client/{quote_token}/quote", json={
                "package_id": bronze["id"], "addon_ids": [], "confirmed": True,
            })
            assert accepted_quote.status_code == 201
            assert accepted_quote.json()["acceptance_email_sent"] is True
            invoice = accepted_quote.json()["invoice"]
            assert invoice["deposit_due_date"] == (date.today() + timedelta(days=1)).isoformat()
            assert invoice["due_date"] == (date(2027, 6, 12) - timedelta(days=45)).isoformat()

            assert client.post(f"/api/client/{quote_token}/forms", json={
                "form_type": "booking_form",
                "data": {
                    "primary_full_name": "Rachel Green", "primary_phone": "07700 900456",
                    "primary_email": "rachel@example.com", "partner_full_name": "Ross Green",
                    "street_address": "1 Test Road", "town": "Manchester", "county": "Greater Manchester",
                    "postcode": "M1 1AA", "wedding_date": "2027-06-12", "ceremony_time": "13:00",
                    "ceremony_details": "Main venue", "reception_details": "Main venue",
                    "package_selected": "Bronze Package 1 2026/27/28", "payment_plan": "standard",
                    "wedding_party_size": "8", "unique_events": "None",
                },
            }).status_code == 200
            assert client.post(f"/api/client/{quote_token}/contract", json={
                "accepted_name": "Rachel Green", "accepted_email": "rachel@example.com",
                "agreed": True,
            }).status_code == 200

            partial_payment = client.post(f"/api/invoices/{invoice['id']}/payments", json={
                "amount": 50, "paid_date": date.today().isoformat(),
                "reference": invoice["number"],
            })
            assert partial_payment.status_code == 201
            assert partial_payment.json()["payment_email_sent"] is True
            assert partial_payment.json()["paid"] == 50
            assert partial_payment.json()["status"] == "part_paid"
            assert partial_payment.json()["balance"] == invoice["total"] - 50

            assert [mail["key"] for mail in journey_emails] == [
                "quote", "quote_accepted", "contract_completed", "payment_received"
            ]
            assert "Wedding Booking Form/questionnaire" in journey_emails[1]["body"]
            assert "digitally sign your wedding contract" in journey_emails[1]["body"]
            assert journey_emails[1]["portal_url"].endswith(f"/client/{quote_token}")
            assert "countersigned by Mark Adam Powell" in journey_emails[2]["body"]
            assert journey_emails[2]["portal_url"].endswith("?tab=agreement")
            payment_mail = journey_emails[3]
        assert payment_mail["values"]["payment_amount"] == "£50.00"
        assert payment_mail["values"]["total_paid"] == "£50.00"
        assert payment_mail["values"]["payment_status"] == "Your booking is secured"
        assert payment_mail["portal_url"].endswith("?tab=invoices")
        secured = client.get(f"/api/bookings/{imported_enquiry[0]['id']}").json()
        assert secured["status"] == "confirmed"


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)

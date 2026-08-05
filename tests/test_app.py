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
from app.models import Booking, Brand, BusinessProfile, Client, ReminderLog


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
                                 "build": "2026.08.05-studio-ninja-manual-only-v8.5"}
        assert client.get("/api/public/config").json() == {
            "google_maps_api_key": None, "google_maps_enabled": False,
        }

        homepage = client.get("/")
        assert homepage.status_code == 200
        assert "Mark's Business Studio" in homepage.text

        assert client.get("/api/dashboard").status_code == 401

        login = client.post("/api/auth/login", json={"email": "mark@example.com", "password": "SecureTestPassword!123"})
        assert login.status_code == 200

        wedding = client.post("/api/bookings", json=booking_payload())
        assert wedding.status_code == 201
        wedding_data = wedding.json()
        assert wedding_data["brand"] == "wbm"
        assert wedding_data["venue_place_id"] == "test-place-peckforton"
        assert wedding_data["venue_address"].startswith("Peckforton Castle")
        assert len(wedding_data["tasks"]) == 7

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
        assert wedding_contract["version"] == "Rev 1.3 - August 2022"
        assert "15. DELIVERY TIME FRAMES AND ALBUMS" in wedding_contract["body"]
        quote_template = next(row for row in templates.json()["templates"]
                              if row["brand"] == "wbm" and row["template_key"] == "quote")
        assert "compare the available packages" in quote_template["body"]
        reminder_keys = {row["template_key"] for row in templates.json()["templates"]
                         if row["brand"] == "wbm" and row["is_active"]}
        assert {"balance_due_10", "balance_due_1", "balance_overdue_2"} <= reminder_keys
        assert not {"balance_due_14", "balance_due_7"} & reminder_keys
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
        assert preview.json()["test_recipient"] == "mark@perfectweddingsbymark.uk"

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
                "partner_full_name": "James Taylor", "street_address": "1 Test Road",
                "town": "Knutsford", "county": "Cheshire", "postcode": "WA16 0AA",
                "wedding_date": "2026-10-04", "ceremony_time": "13:00",
                "package_selected": "Platinum Package 4 2026/27/28",
                "payment_options": ["Booking fee due within one day of accepting the quote; remaining balance due 45 days before the wedding"],
            }
        })
        assert form.status_code == 200
        accepted = client.post(f"/api/client/{token}/contract", json={
            "accepted_name": "Sophie Taylor", "accepted_email": "wbm@example.com", "agreed": True
        })
        assert accepted.status_code == 200
        portal_status = client.get(f"/api/bookings/{wedding_data['id']}/portal").json()
        assert portal_status["contract"]["accepted_name"] == "Sophie Taylor"
        assert portal_status["submissions"][0]["form_type"] == "booking_form"
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
            "amount": 999, "paid_date": "2026-08-03", "reference": "WBM02001"
        })
        assert payment.status_code == 201
        assert payment.json()["status"] == "paid"
        assert payment.json()["balance"] == 0

        pdf = client.get(f"/api/invoices/{wbm_invoice.json()['id']}/pdf")
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")
        receipt = client.get(f"/api/invoices/{wbm_invoice.json()['id']}/receipt.pdf")
        assert receipt.status_code == 200

        invoices = client.get("/api/invoices").json()
        assert {row["number"] for row in invoices} == {"ID02001", "WBM02001"}

        catalog = client.get("/api/catalog?brand=wbm").json()
        assert [row["price"] for row in catalog["packages"]] == [475, 699, 899, 1299, 1699]
        album = next(row for row in catalog["addons"] if row["code"] == "album_offer")
        speeches = next(row for row in catalog["addons"] if row["code"] == "speeches")
        assert album["price"] == 120
        gold = next(row for row in catalog["packages"] if row["code"] == "gold")
        assert client.post(f"/api/client/{token}/quote", json={
            "package_id": gold["id"], "addon_ids": [speeches["id"]], "confirmed": True
        }).status_code == 422
        quote = client.post(f"/api/client/{token}/quote", json={
            "package_id": gold["id"], "addon_ids": [album["id"]], "confirmed": True
        })
        assert quote.status_code == 201
        assert quote.json()["quote"]["total"] == 1019
        assert quote.json()["invoice"]["number"] == "WBM02002"
        assert quote.json()["acceptance_email_sent"] is False
        expected_deposit_due = date.today() + timedelta(days=1)
        expected_balance_due = max(date(2026, 10, 4) - timedelta(days=45), expected_deposit_due)
        assert quote.json()["invoice"]["deposit_due_date"] == expected_deposit_due.isoformat()
        assert quote.json()["invoice"]["due_date"] == expected_balance_due.isoformat()
        assert [line["name"] for line in quote.json()["invoice"]["line_items"]] == [
            "Gold Package 3 2026/27/28", "Wedding album offer"
        ]
        assert "Highlight Video" in quote.json()["invoice"]["line_items"][0]["description"]
        refreshed_public = client.get(f"/api/client/{token}").json()
        assert refreshed_public["quote"]["invoice_number"] == "WBM02002"
        assert refreshed_public["record"]["quoted_total"] == 1019
        assert refreshed_public["invoices"][0]["number"] == "WBM02002"
        assert refreshed_public["invoices"][0]["deposit_due_date"] == expected_deposit_due.isoformat()
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
                (expected_balance_due - timedelta(days=10), "balance_due_10"),
                (expected_balance_due - timedelta(days=1), "balance_due_1"),
                (expected_balance_due + timedelta(days=2), "balance_overdue_2"),
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
                FrozenDate.current = expected_balance_due - timedelta(days=10)
                assert main_module.run_due_reminders(db) == {"sent": 0, "skipped": 0, "failed": 0}
                paid_invoice.paid = 0
                paid_invoice.status = "unpaid"
                db.commit()

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["confirmed"] == 1
        assert dashboard.json()["open_tasks"] == 11

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
        assert "let the countdown to your best day ever begin" in enquiry_page.text
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
                "data": {"primary_full_name": "Rachel Green", "primary_phone": "07700 900456"},
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
            "quote", "quote_accepted", "payment_received"
        ]
        assert "Wedding Booking Form/questionnaire" in journey_emails[1]["body"]
        assert "digitally sign your wedding contract" in journey_emails[1]["body"]
        assert journey_emails[1]["portal_url"].endswith(f"/client/{quote_token}")
        payment_mail = journey_emails[2]
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

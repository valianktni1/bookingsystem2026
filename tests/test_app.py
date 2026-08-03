import os
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

from app.main import app


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
        "package_name": "Platinum" if brand == "wbm" else "Website + CMS",
        "quoted_total": 1299 if brand == "wbm" else 399,
        "deposit_amount": 300 if brand == "wbm" else 0,
        "deposit_paid_date": "2026-01-18" if brand == "wbm" else None,
    }


def test_phase_two_b_flow():
    db_file = TEST_ROOT / "test.db"
    db_file.unlink(missing_ok=True)
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "phase": "2B", "smtp_configured": False,
                                 "reminders_enabled": False,
                                 "build": "2026.08.03-portal-invoices-v3"}

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
        assert len(wedding_data["tasks"]) == 7

        templates = client.get("/api/communications/templates")
        assert templates.status_code == 200
        assert len(templates.json()["templates"]) >= 10
        assert len(templates.json()["contracts"]) == 2
        wedding_contract = next(row for row in templates.json()["contracts"] if row["brand"] == "wbm")
        assert wedding_contract["title"] == "Weddings By Mark Contract"
        assert wedding_contract["version"] == "Rev 1.3 - August 2022"
        assert "15. DELIVERY TIME FRAMES AND ALBUMS" in wedding_contract["body"]
        quote_template = next(row for row in templates.json()["templates"]
                              if row["brand"] == "wbm" and row["template_key"] == "quote")
        assert "compare the available packages" in quote_template["body"]

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
                "payment_options": ["£100 deposit + balance 45 days before the wedding"],
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
        assert ivory_invoice.json()["number"] == "ID02002"
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
        assert [row["number"] for row in invoices] == ["ID02002", "WBM02001"]

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
        assert quote.json()["invoice"]["number"] == "WBM02003"
        assert quote.json()["acceptance_email_sent"] is False
        assert [line["name"] for line in quote.json()["invoice"]["line_items"]] == [
            "Gold Package 3 2026/27/28", "Wedding album offer"
        ]
        refreshed_public = client.get(f"/api/client/{token}").json()
        assert refreshed_public["quote"]["invoice_number"] == "WBM02003"
        assert refreshed_public["record"]["quoted_total"] == 1019
        assert refreshed_public["invoices"][0]["number"] == "WBM02003"
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
            "package_interest": "Gold Package 3 2026/27/28",
            "selfie_booth_interest": "maybe", "message": "Relaxed summer wedding",
            "promo_code": None, "heard_about_us": "Google search",
            "fun_answer": "Beans on toast", "privacy_agreed": True, "website": None,
        }
        enquiry = client.post("/api/public/enquiries", json=enquiry_payload)
        assert enquiry.status_code == 201
        assert enquiry.json()["ok"] is True
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123"
        }).status_code == 200
        imported_enquiry = client.get("/api/bookings?q=Rachel").json()
        assert len(imported_enquiry) == 1
        assert imported_enquiry[0]["status"] == "enquiry"
        assert imported_enquiry[0]["venue_or_project"] == "Lytham Hall"


def teardown_module():
    (TEST_ROOT / "test.db").unlink(missing_ok=True)

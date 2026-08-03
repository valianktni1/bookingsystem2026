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


def test_phase_two_a_flow():
    db_file = TEST_ROOT / "test.db"
    db_file.unlink(missing_ok=True)
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "phase": "2A"}

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

        ivory_invoice = client.post(f"/api/bookings/{digital_data['id']}/invoices", json={"total": 399, "paid": 399, "issue_date": "2026-01-19"})
        assert ivory_invoice.status_code == 201
        assert ivory_invoice.json()["number"] == "ID02002"
        assert ivory_invoice.json()["status"] == "paid"

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

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["confirmed"] == 1
        assert dashboard.json()["open_tasks"] == 14

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


def teardown_module():
    (TEST_ROOT / "test.db").unlink(missing_ok=True)

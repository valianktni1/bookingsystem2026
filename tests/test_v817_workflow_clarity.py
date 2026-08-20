import os
from datetime import date, timedelta
from pathlib import Path


TEST_ROOT = Path(__file__).parent
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test-v817.db'}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v817-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "v817-test-session-secret-at-least-32-characters"

from fastapi.testclient import TestClient

from app.database import engine
from app.main import app


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test-v817.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v817.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com", "password": "SecureTestPassword!123",
    }).status_code == 200


def create_booking(client, title, event_days):
    return client.post("/api/bookings", json={
        "brand": "wbm", "kind": "wedding", "status": "confirmed",
        "title": title,
        "client": {
            "first_name": title.split()[0], "last_name": "Test",
            "partner_name": "Partner", "email": f"{title.split()[0].lower()}@example.com",
        },
        "event_date": (date.today() + timedelta(days=event_days)).isoformat(),
        "venue_or_project": "Test Hall", "quoted_total": 899, "deposit_amount": 100,
    }).json()


def add_invoice(client, booking_id, due_days):
    response = client.post(f"/api/bookings/{booking_id}/invoices", json={
        "total": 899, "paid": 100,
        "issue_date": date.today().isoformat(),
        "due_date": (date.today() + timedelta(days=due_days)).isoformat(),
        "description": "Wedding photography",
    })
    assert response.status_code == 201, response.text


def test_upcoming_payments_cover_60_days_without_expanding_final_call_window():
    reset_database()
    with TestClient(app) as client:
        login(client)
        inside = create_booking(client, "Inside Couple", 50)
        outside = create_booking(client, "Outside Couple", 120)
        add_invoice(client, inside["id"], 45)
        add_invoice(client, outside["id"], 61)

        queues = client.get("/api/workflow-queues").json()["queues"]
        payment_ids = {row["booking_id"] for row in queues["payments_due"]}
        final_call_ids = {row["booking_id"] for row in queues["final_calls"]}
        assert inside["id"] in payment_ids
        assert outside["id"] not in payment_ids
        # This booking's private call is due in 20 days, so the original
        # 14-day operational window remains unchanged.
        assert inside["id"] not in final_call_ids


def test_template_manager_reports_real_workflow_usage_and_retry_control():
    reset_database()
    with TestClient(app) as client:
        login(client)
        rows = client.get("/api/communications/templates?brand=wbm").json()["templates"]
        by_key = {row["template_key"]: row for row in rows}
        assert by_key["enquiry_received"]["usage_kind"] == "automatic"
        assert by_key["quote"]["usage_kind"] == "action"
        assert by_key["booking_link"]["usage_kind"] == "manual"
        assert by_key["contract_completed"]["usage_kind"] == "automatic"
        assert by_key["balance_due_10"]["usage_kind"] == "inactive"

        dashboard_js = client.get("/static/v811.js").text
        assert "Due within the next 60 days" in dashboard_js
        assert "Hostinger temporarily refused this message" in dashboard_js
        assert "data-retry-contract-email" in dashboard_js


def teardown_module():
    engine.dispose()
    (TEST_ROOT / "test-v817.db").unlink(missing_ok=True)
    (TEST_ROOT / "test-v817.db-journal").unlink(missing_ok=True)

import base64
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


TEST_ROOT = Path(__file__).parent
DB_FILE = TEST_ROOT / "test-v849.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v849-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"


from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal, engine
from app.main import app
from app.models import Booking, EmailLog, SmsMessage, SmsTemplate, Task
import app.sms_routes as routes
import app.sms_service as service


def reset_database():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v849.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com",
        "password": "SecureTestPassword!123",
    }).status_code == 200


def create_booking(client, *, title="SMS Couple", phone="07712 345678"):
    response = client.post("/api/bookings", json={
        "brand": "wbm",
        "kind": "wedding",
        "status": "quoted",
        "title": title,
        "client": {
            "first_name": "Sophie",
            "last_name": "Taylor",
            "partner_name": "James",
            "email": "sms-couple@example.com",
            "phone": phone,
        },
        "event_date": (date.today() + timedelta(days=180)).isoformat(),
        "venue_or_project": "SMS Hall",
        "quoted_total": 699,
        "deposit_amount": 100,
    })
    assert response.status_code == 201, response.text
    return response.json()


def enable_mock_sms(monkeypatch):
    monkeypatch.setattr(service.settings, "sms_enabled", True)
    monkeypatch.setattr(service.settings, "sms_api_token", "mock-token-long-enough-for-tests")
    monkeypatch.setattr(service.settings, "sms_sender_id", "WedsByMark")
    monkeypatch.setattr(service.settings, "sms_reply_number", None)
    monkeypatch.setattr(routes.settings, "sms_enabled", True)
    monkeypatch.setattr(routes.settings, "sms_api_token", "mock-token-long-enough-for-tests")


def test_sms_is_safe_by_default_and_templates_are_seeded_inactive():
    reset_database()
    with TestClient(app) as client:
        login(client)
        status = client.get("/api/sms/status")
        assert status.status_code == 200
        assert status.json()["enabled"] is False
        assert status.json()["automatic_enabled"] is False
        booking = create_booking(client, title="Safely Off Couple")
        blocked = client.post(f"/api/bookings/{booking['id']}/sms/send", json={
            "body": "This must remain unsent", "confirmed": True,
        })
        assert blocked.status_code == 503
        templates = client.get("/api/sms/templates?brand=wbm").json()["templates"]
        assert next(row for row in templates if row["template_key"] == "manual_message")["is_active"] is True
        automatic = [row for row in templates if row["is_automatic"]]
        assert len(automatic) == 7
        assert all(row["is_active"] is False for row in automatic)


def test_manual_send_is_confirmed_normalised_persisted_and_audited(monkeypatch):
    reset_database()
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return {"messageid": "provider-out-849"}

    enable_mock_sms(monkeypatch)
    monkeypatch.setattr(service, "provider_send_sms", fake_send)
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        unconfirmed = client.post(f"/api/bookings/{booking['id']}/sms/send", json={
            "body": "Hi Sophie, this should not send.", "confirmed": False,
        })
        assert unconfirmed.status_code == 422
        response = client.post(f"/api/bookings/{booking['id']}/sms/send", json={
            "body": "Hi Sophie, your wedding message is ready. Mark",
            "template_key": "manual_message",
            "confirmed": True,
        })
        assert response.status_code == 201, response.text
        assert sent[0]["destination"] == "447712345678"
        assert sent[0]["sender"] == "WedsByMark"
        assert {item["key"] for item in sent[0]["metadata"]} == {"booking_id", "sms_message_id"}
        centre = client.get(f"/api/bookings/{booking['id']}/sms").json()
        assert centre["messages"][0]["status"] == "sent"
        assert centre["messages"][0]["provider_message_id"] == "provider-out-849"


def test_provider_request_uses_official_endpoint_jwt_header_and_metadata(monkeypatch):
    enable_mock_sms(monkeypatch)
    captured = {}

    class FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"messageid":"official-contract-849"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = request.data.decode()
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(service.urllib.request, "urlopen", fake_urlopen)
    result = service.provider_send_sms(
        destination="447712345678",
        sender="WedsByMark",
        content="Contract test",
        metadata=[{"key": "booking_id", "value": "booking-849"}],
    )
    assert result["messageid"] == "official-contract-849"
    assert captured["url"] == "https://api.thesmsworks.co.uk/v1/message/send"
    assert captured["authorization"] == "mock-token-long-enough-for-tests"
    assert '"ai": false' in captured["body"]
    assert '"booking_id"' in captured["body"]


def test_failed_send_is_retained_and_does_not_change_booking(monkeypatch):
    reset_database()
    enable_mock_sms(monkeypatch)

    def fail_send(**_kwargs):
        raise service.SmsDeliveryError("provider unavailable")

    monkeypatch.setattr(service, "provider_send_sms", fail_send)
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        before = client.get(f"/api/bookings/{booking['id']}").json()
        response = client.post(f"/api/bookings/{booking['id']}/sms/send", json={
            "body": "Hi Sophie, a retained failed message.", "confirmed": True,
        })
        assert response.status_code == 503
        after = client.get(f"/api/bookings/{booking['id']}").json()
        assert after["status"] == before["status"]
        assert after["quoted_total"] == before["quoted_total"]
        with SessionLocal() as db:
            row = db.scalar(select(SmsMessage).where(SmsMessage.booking_id == booking["id"]))
            assert row.status == "failed"
            assert "provider unavailable" in row.error


def test_test_booking_can_only_send_to_nominated_test_mobile(monkeypatch):
    reset_database()
    calls = []
    enable_mock_sms(monkeypatch)
    monkeypatch.setattr(service.settings, "sms_test_number", "07700 900123")
    monkeypatch.setattr(routes.settings, "sms_test_number", "07700 900123")
    monkeypatch.setattr(service, "provider_send_sms", lambda **kwargs: calls.append(kwargs) or {
        "messageid": "test-redirect-849"
    })
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client, title="Test SMS Couple", phone="07712 345678")
        with SessionLocal() as db:
            row = db.get(Booking, booking["id"])
            row.is_test = True
            db.commit()
        response = client.post(f"/api/bookings/{booking['id']}/sms/send", json={
            "body": "Safe test message", "confirmed": True,
        })
        assert response.status_code == 201, response.text
        assert calls[0]["destination"] == "447700900123"
        assert calls[0]["destination"] != "447712345678"


def test_incoming_reply_is_authenticated_idempotent_and_attached(monkeypatch):
    reset_database()
    enable_mock_sms(monkeypatch)
    monkeypatch.setattr(routes.settings, "sms_webhook_username", "sms-hook")
    monkeypatch.setattr(routes.settings, "sms_webhook_password", "strong-hook-password")
    auth = "Basic " + base64.b64encode(b"sms-hook:strong-hook-password").decode()
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        payload = {
            "content": "Thanks Mark, we have received it.",
            "from": "447712345678",
            "to": "447700900000",
            "messageid": "provider-in-849",
            "messagetype": "incoming",
            "parts": 1,
            "metadata": {"booking_id": booking["id"]},
        }
        assert client.post("/api/integrations/smsworks/incoming", json=payload).status_code == 401
        first = client.post("/api/integrations/smsworks/incoming", json=payload, headers={"Authorization": auth})
        assert first.status_code == 200
        assert first.json() == {"ok": True, "duplicate": False, "matched": True}
        duplicate = client.post("/api/integrations/smsworks/incoming", json=payload, headers={"Authorization": auth})
        assert duplicate.json()["duplicate"] is True
        centre = client.get(f"/api/bookings/{booking['id']}/sms").json()
        assert len(centre["messages"]) == 1
        assert centre["messages"][0]["direction"] == "incoming"
        with SessionLocal() as db:
            tasks = db.scalars(select(Task).where(Task.booking_id == booking["id"],
                                                  Task.workflow_key.like("sms_reply:%"))).all()
            assert len(tasks) == 1


def test_delivery_report_updates_exact_message(monkeypatch):
    reset_database()
    enable_mock_sms(monkeypatch)
    monkeypatch.setattr(routes.settings, "sms_webhook_username", "sms-hook")
    monkeypatch.setattr(routes.settings, "sms_webhook_password", "strong-hook-password")
    monkeypatch.setattr(service, "provider_send_sms", lambda **_: {"messageid": "delivery-849"})
    auth = "Basic " + base64.b64encode(b"sms-hook:strong-hook-password").decode()
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        assert client.post(f"/api/bookings/{booking['id']}/sms/send", json={
            "body": "Delivery test", "confirmed": True,
        }).status_code == 201
        delivered = client.post("/api/integrations/smsworks/delivery", headers={"Authorization": auth}, json={
            "messageid": "delivery-849", "status": "DELIVERED", "messageparts": "1",
        })
        assert delivered.status_code == 200
        centre = client.get(f"/api/bookings/{booking['id']}/sms").json()
        assert centre["messages"][0]["status"] == "delivered"
        assert centre["messages"][0]["delivered_at"]


def test_individual_sms_pauses_do_not_change_email_followups():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        response = client.put(
            f"/api/bookings/{booking['id']}/sms/automations/quote_followup_1",
            json={"paused": True},
        )
        assert response.status_code == 200
        centre = client.get(f"/api/bookings/{booking['id']}/sms").json()
        controls = {row["template_key"]: row for row in centre["automations"]}
        assert controls["quote_followup_1"]["paused"] is True
        assert controls["quote_followup_final"]["paused"] is False
        record = client.get(f"/api/bookings/{booking['id']}").json()
        assert "quote_followup_controls" not in record["workflow_state"]


def test_automatic_sms_requires_master_and_active_template(monkeypatch):
    reset_database()
    calls = []
    enable_mock_sms(monkeypatch)
    monkeypatch.setattr(service, "provider_send_sms", lambda **kwargs: calls.append(kwargs) or {"messageid": "auto-849"})
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        with SessionLocal() as db:
            db.add(EmailLog(
                booking_id=booking["id"], template_key="quote", recipient="sms-couple@example.com",
                subject="Quote", body="Quote", status="sent",
                sent_at=datetime.now(timezone.utc) - timedelta(days=1),
            ))
            template = db.scalar(select(SmsTemplate).where(
                SmsTemplate.template_key == "quote_followup_1"
            ))
            template.is_active = True
            db.commit()
            assert routes.run_due_sms_automations(db)["enabled"] is False
        assert calls == []
        monkeypatch.setattr(routes.settings, "sms_automatic_enabled", True)
        with SessionLocal() as db:
            result = routes.run_due_sms_automations(db)
            assert result["sent"] == 1
            assert routes.run_due_sms_automations(db)["skipped"] >= 1
        assert len(calls) == 1


def test_v849_frontend_is_visible_and_mobile_ready():
    index = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    javascript = (Path(__file__).parents[1] / "app" / "static" / "v849.js").read_text()
    css = (Path(__file__).parents[1] / "app" / "static" / "v849.css").read_text()
    workspace = (Path(__file__).parents[1] / "app" / "static" / "v844.js").read_text()
    assert "BOOKINGSYSTEM2026 · COMPLETE V8.49" in index
    assert "/static/v849.js?v=sms-centre-v8-49" in index
    assert 'Texts: "texts"' in workspace
    assert "Pause each text separately" in javascript
    assert "Your existing email reminders continue exactly as before" in javascript
    assert "@media(max-width:760px)" in css

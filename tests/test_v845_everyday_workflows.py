import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path


TEST_ROOT = Path(__file__).parent
ROOT = TEST_ROOT.parent
DB_FILE = TEST_ROOT / "test-v845.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "v845-storage")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_EMAIL"] = "mark@example.com"
os.environ["ADMIN_PASSWORD"] = "SecureTestPassword!123"
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-characters-long"


from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.main as main_module
import app.v845_routes as v845_routes
from app.database import SessionLocal, engine
from app.main import app
from app.models import (
    AuditLog,
    Booking,
    ContractAcceptance,
    DateBlock,
    EmailLog,
    Invoice,
    Quote,
    ReminderLog,
    Task,
)


def reset_database():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v845.db-journal").unlink(missing_ok=True)


def login(client):
    assert client.post("/api/auth/login", json={
        "email": "mark@example.com",
        "password": "SecureTestPassword!123",
    }).status_code == 200


def create_booking(client, *, title="Alice & Ben", status="quoted", event_date=None):
    response = client.post("/api/bookings", json={
        "brand": "wbm",
        "kind": "wedding",
        "status": status,
        "title": title,
        "client": {
            "first_name": title.split()[0],
            "last_name": "Client",
            "partner_name": "Partner",
            "email": f"{title.split()[0].lower()}-v845@example.com",
        },
        "event_date": (event_date or (date.today() + timedelta(days=200))).isoformat(),
        "venue_or_project": "Test Hall",
        "quoted_total": 900,
        "deposit_amount": 100,
        "deposit_paid_date": date.today().isoformat() if status == "confirmed" else None,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_unsuccessful_enquiry_closes_and_reopens_without_email_or_financial_change():
    reset_database()
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client)
        portal = client.post(f"/api/bookings/{booking['id']}/portal", json={
            "expires_days": 365,
        }).json()
        token = portal["url"].split("/client/")[1]
        before = client.get(f"/api/bookings/{booking['id']}").json()
        open_task_ids = {row["id"] for row in before["tasks"] if not row["completed"]}
        with SessionLocal() as db:
            email_count = db.scalar(select(func.count()).select_from(EmailLog))

        closed = client.post(f"/api/bookings/{booking['id']}/close-enquiry", json={
            "outcome": "booked_elsewhere",
            "details": "Couple let Mark know by email",
        })
        assert closed.status_code == 200, closed.text
        assert closed.json()["message"].endswith("no client email sent")
        record = client.get(f"/api/bookings/{booking['id']}").json()
        assert record["status"] == "quoted"
        assert record["archived"] is True
        assert record["automation_suppressed"] is True
        assert record["workflow_state"]["enquiry_closure"]["outcome_label"] == "Booked another photographer"
        assert all(row["completed"] for row in record["tasks"])
        assert client.get(f"/api/client/{token}").status_code == 404
        assert client.post(f"/api/bookings/{booking['id']}/restore").status_code == 409
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(EmailLog)) == email_count

        reopened = client.post(f"/api/bookings/{booking['id']}/reopen-enquiry")
        assert reopened.status_code == 200, reopened.text
        restored = client.get(f"/api/bookings/{booking['id']}").json()
        assert restored["status"] == "quoted"
        assert restored["archived"] is False
        assert restored["automation_suppressed"] is False
        assert open_task_ids == {row["id"] for row in restored["tasks"] if not row["completed"]}
        assert "enquiry_closure" not in restored["workflow_state"]
        assert len(restored["workflow_state"]["enquiry_closure_history"]) == 1
        assert client.get(f"/api/client/{token}").status_code == 404


def test_booked_wedding_moves_date_without_rewriting_invoice_payment_or_agreement():
    reset_database()
    old_date = date.today() + timedelta(days=200)
    new_date = date.today() + timedelta(days=300)
    agreed_due = date.today() + timedelta(days=230)
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client, title="Cara & Dan", status="confirmed", event_date=old_date)
        invoice_response = client.post(f"/api/bookings/{booking['id']}/invoices", json={
            "total": 900,
            "paid": 100,
            "issue_date": date.today().isoformat(),
            "deposit_due_date": date.today().isoformat(),
            "supply_date": old_date.isoformat(),
            "due_date": agreed_due.isoformat(),
            "description": "Gold wedding package",
        })
        assert invoice_response.status_code == 201, invoice_response.text
        invoice = invoice_response.json()
        accepted_at = datetime.now(timezone.utc) - timedelta(days=10)
        with SessionLocal() as db:
            row = db.get(Booking, booking["id"])
            row.balance_due_date = agreed_due
            db.add(Quote(
                booking_id=row.id,
                status="accepted",
                total=Decimal("900"),
                deposit_amount=Decimal("100"),
                invoice_id=invoice["id"],
                accepted_at=accepted_at,
            ))
            db.add(ContractAcceptance(
                booking_id=row.id,
                contract_title="Wedding agreement",
                contract_version="1.4",
                contract_body="Protected original agreement text",
                accepted_name="Cara Client",
                accepted_email="cara-v845@example.com",
                accepted_at=accepted_at,
            ))
            db.add(DateBlock(
                start_date=new_date,
                end_date=new_date,
                label="Private family day",
            ))
            db.add(ReminderLog(
                booking_id=row.id,
                reminder_key="check_in_120",
                scheduled_for=old_date - timedelta(days=120),
                status="failed",
                error="Temporary test failure",
            ))
            db.commit()

        check = client.get(
            f"/api/bookings/{booking['id']}/reschedule-check",
            params={"new_date": new_date.isoformat()},
        )
        assert check.status_code == 200
        assert check.json()["conflicts"]["count"] == 1
        blocked = client.post(f"/api/bookings/{booking['id']}/reschedule", json={
            "new_date": new_date.isoformat(),
            "reason": "The couple postponed their wedding",
            "confirm_conflicts": False,
        })
        assert blocked.status_code == 409

        moved = client.post(f"/api/bookings/{booking['id']}/reschedule", json={
            "new_date": new_date.isoformat(),
            "reason": "The couple postponed their wedding",
            "confirm_conflicts": True,
        })
        assert moved.status_code == 200, moved.text
        assert moved.json()["message"].endswith("no client email sent")
        record = client.get(f"/api/bookings/{booking['id']}").json()
        updated_invoice = next(row for row in record["invoices"] if row["id"] == invoice["id"])
        assert record["event_date"] == new_date.isoformat()
        assert record["balance_due_date"] == agreed_due.isoformat()
        assert updated_invoice["number"] == invoice["number"]
        assert updated_invoice["paid"] == 100
        assert updated_invoice["supply_date"] == new_date.isoformat()
        assert updated_invoice["due_date"] == agreed_due.isoformat()
        assert record["workflow_state"]["reschedule_history"][-1]["old_date"] == old_date.isoformat()
        assert any(
            row["workflow_key"] == "wbm_reschedule_agreement_review" and not row["completed"]
            for row in record["tasks"]
        )
        with SessionLocal() as db:
            agreement = db.scalar(select(ContractAcceptance).where(
                ContractAcceptance.booking_id == booking["id"]
            ))
            assert agreement.contract_body == "Protected original agreement text"
            reminder = db.scalar(select(ReminderLog).where(
                ReminderLog.booking_id == booking["id"],
                ReminderLog.reminder_key == "check_in_120",
            ))
            assert reminder.status == "superseded"
            audit = db.scalar(select(AuditLog).where(
                AuditLog.entity_id == booking["id"],
                AuditLog.action == "reschedule_wedding",
            ))
            assert audit.details["invoice_numbers_retained"] == [invoice["number"]]
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 0


def test_real_reply_pauses_only_next_day_quote_check(monkeypatch):
    reset_database()
    today = date.today()
    quote_sent = datetime.combine(today - timedelta(days=1), time(10, 0), tzinfo=timezone.utc)
    with TestClient(app) as client:
        login(client)
        booking = create_booking(client, title="Ella & Finn")
        with SessionLocal() as db:
            db.add(EmailLog(
                booking_id=booking["id"],
                template_key="quote",
                recipient="ella-v845@example.com",
                subject="Your wedding quote",
                body="Quote body",
                status="sent",
                sent_at=quote_sent,
            ))
            db.commit()

        monkeypatch.setattr(v845_routes, "imap_ready", lambda brand: True)
        monkeypatch.setattr(v845_routes, "list_inbox_messages", lambda brand, limit=200: [{
            "uid": "84501",
            "reply_to_email": "ella-v845@example.com",
            "date": (quote_sent + timedelta(hours=2)).isoformat(),
        }])
        monkeypatch.setattr(
            main_module,
            "send_template_email",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("No follow-up should send")),
        )
        with SessionLocal() as db:
            result = main_module.run_due_reminders(db)
            assert result == {"sent": 0, "skipped": 0, "failed": 0}

        portal = client.get(f"/api/bookings/{booking['id']}/portal").json()
        controls = {row["reminder_key"]: row for row in portal["quote_followups"]}
        assert controls["quote_followup_1"]["status"] == "paused"
        assert controls["quote_followup_final"]["status"] == "active"
        assert portal["quote_reply_detection"]["next_day_followup_paused"] is True
        assert portal["quote_reply_detection"]["final_followup_unchanged"] is True


def test_v845_interface_and_template_contracts():
    index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/v845.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "app/static/v845.css").read_text(encoding="utf-8")
    bootstrap = (ROOT / "app/bootstrap.py").read_text(encoding="utf-8")
    release = (ROOT / "RELEASE-NOTES-V8.45.md").read_text(encoding="utf-8")

    assert "BOOKINGSYSTEM2026 · COMPLETE V8.47" in index
    assert index.index("v844.js") < index.index("v845.js")
    assert "/static/v845.css?v=everyday-workflows-v8-45" in index
    assert "Close unsuccessful enquiry" in script
    assert "Move wedding date" in script
    assert "Review & send form reminder" in script
    assert "Review & send agreement reminder" in script
    assert "final nine-day check remains independent" in script
    assert ".v845-chaser-panel" in stylesheet
    assert '"booking_form_reminder"' in bootstrap
    assert "No client email is sent" in release


def teardown_module():
    engine.dispose()
    DB_FILE.unlink(missing_ok=True)
    (TEST_ROOT / "test-v845.db-journal").unlink(missing_ok=True)

import os
from datetime import date
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
from app.models import Booking, ClientPortalToken, EmailLog, Invoice, InvoiceCounter, Payment, ReminderLog


def archive_payload():
    return {
        "confirmation": "IMPORT ARCHIVE WITHOUT EMAILS",
        "record": {
            "legacy_id": "completed-jobs.csv:44",
            "import_batch": "studio-ninja-complete-archive-2026-08-06",
            "brand": "wbm",
            "kind": "wedding",
            "title": "Historic & Couple",
            "status": "completed",
            "archived": True,
            "source_created_at": "2023-01-01T12:00:00+00:00",
            "event_date": "2024-05-18",
            "venue_or_project": "Historic Hall",
            "package_name": "Historic wedding package",
            "quoted_total": 975,
            "deposit_amount": 100,
            "client": {
                "first_name": "Historic",
                "last_name": "Client",
                "partner_name": "Couple Client",
                "email": "historic@example.com",
            },
            "invoices": [{
                "number": "WBM01706",
                "sequence": 1706,
                "legacy_number": "WBM01706",
                "issue_date": "2023-01-02",
                "supply_date": "2024-05-18",
                "description": "Wedding package",
                "total": 900,
                "paid": 900,
                "status": "paid",
                "line_items": [{"name": "Wedding package", "quantity": 1, "unit_price": 900, "total": 900}],
                "payments": [{
                    "amount": 100,
                    "paid_date": "2023-01-02",
                    "reference": "WBM01706",
                    "legacy_reference": "WBM01706:archive-payment:1",
                }, {
                    "amount": 800,
                    "paid_date": "2024-04-03",
                    "reference": "WBM01706",
                    "legacy_reference": "WBM01706:archive-payment:2",
                }],
            }, {
                "number": "WBM01707",
                "sequence": 1707,
                "legacy_number": "WBM01707",
                "issue_date": "2024-04-04",
                "supply_date": "2024-05-18",
                "description": "Album add-on",
                "total": 75,
                "paid": 75,
                "status": "paid",
                "line_items": [{"name": "Album", "quantity": 1, "unit_price": 75, "total": 75}],
                "payments": [{
                    "amount": 75,
                    "paid_date": "2024-04-04",
                    "reference": "WBM01707",
                    "legacy_reference": "WBM01707:archive-payment:1",
                }],
            }],
            "quotes": [{
                "legacy_number": "Q01706",
                "status": "accepted",
                "accepted_at": "2023-01-02T12:00:00+00:00",
                "created_at": "2023-01-01T12:00:00+00:00",
                "linked_invoice_number": "WBM01706",
                "total": 900,
                "deposit_amount": 100,
            }],
            "booking_form": {
                "data": {"ceremony_time": "13:00", "second_venue": "Reception Barn"},
                "submitted_at": "2023-01-02T12:00:00+00:00",
            },
            "contract": {
                "accepted_at": "2023-01-02T12:00:00+00:00",
                "accepted_name": "Historic Client",
                "accepted_email": "historic@example.com",
                "date_source": "questionnaire_completed_date",
            },
            "legacy_timeline": [{
                "date": "2023-01-02",
                "type": "payment_received",
                "detail": "Booking payment retained",
            }],
        },
    }


def test_complete_archive_import_preserves_numbers_and_live_counter():
    db_file = TEST_ROOT / "test.db"
    engine.dispose()
    db_file.unlink(missing_ok=True)
    (db_file.parent / "test.db-journal").unlink(missing_ok=True)

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200

        readiness = client.get("/api/legacy-import/archive/readiness").json()
        assert readiness["mode"] == "protected_archive_no_email"
        assert readiness["live_invoice_counters_will_change"] is False

        payload = archive_payload()
        validated = client.post("/api/legacy-import/archive/validate", json=payload)
        assert validated.status_code == 200, validated.text
        assert validated.json()["invoice_count"] == 2
        assert validated.json()["invoice_conflicts"] == []

        imported = client.post("/api/legacy-import/archive/records", json=payload)
        assert imported.status_code == 201, imported.text
        result = imported.json()
        assert result["invoice_numbers"] == ["WBM01706", "WBM01707"]
        assert result["invoice_counters_changed"] is False
        booking_id = result["booking_id"]

        # Historic invoices are retained inside the archived record without
        # overwhelming the day-to-day active payment register.
        assert client.get("/api/invoices").json() == []
        assert {row["number"] for row in client.get("/api/invoices?archived=true").json()} == {
            "WBM01706", "WBM01707",
        }

        record = client.get(f"/api/bookings/{booking_id}").json()
        assert record["archived"] is True
        assert record["automation_suppressed"] is True
        assert {row["number"] for row in record["invoices"]} == {"WBM01706", "WBM01707"}
        assert sum(len(row["payments"]) for row in record["invoices"]) == 3
        assert client.get(f"/api/bookings/{booking_id}/portal").json()["submissions"][0]["data"]["second_venue"] == "Reception Barn"

        dashboard = client.get("/api/dashboard").json()
        assert dashboard["confirmed"] == 0
        assert dashboard["upcoming"] == []

        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Booking)) == 1
            assert db.scalar(select(func.count()).select_from(Invoice)) == 2
            assert db.scalar(select(func.count()).select_from(Payment)) == 3
            assert db.scalar(select(func.count()).select_from(ClientPortalToken)) == 0
            assert db.scalar(select(func.count()).select_from(EmailLog)) == 0
            assert db.scalar(select(func.count()).select_from(ReminderLog)) == 0
            counters = {row.key: row.value for row in db.scalars(select(InvoiceCounter)).all()}
            assert "brand:wbm" not in counters

        assert client.post("/api/legacy-import/archive/records", json=payload).status_code == 409
        duplicate = client.post("/api/legacy-import/archive/validate", json=payload).json()
        assert duplicate["duplicate"] is True

        fresh = client.post("/api/bookings", json={
            "brand": "wbm", "kind": "wedding", "status": "confirmed",
            "title": "New & Wedding", "client": {
                "first_name": "New", "last_name": "Client", "email": "new@example.com",
            }, "event_date": date.today().isoformat(), "venue_or_project": "New Venue",
            "quoted_total": 699, "deposit_amount": 100,
        })
        assert fresh.status_code == 201
        new_invoice = client.post(f"/api/bookings/{fresh.json()['id']}/invoices", json={
            "total": 699, "paid": 0, "issue_date": date.today().isoformat(),
        })
        assert new_invoice.status_code == 201, new_invoice.text
        assert new_invoice.json()["number"] == "WBM02001"

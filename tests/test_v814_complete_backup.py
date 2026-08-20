import hashlib
import io
import json
import os
import zipfile
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

from app.database import SessionLocal, engine
from app.main import app
from app.models import SystemSetting


def reset_database():
    engine.dispose()
    (TEST_ROOT / "test.db").unlink(missing_ok=True)
    (TEST_ROOT / "test.db-journal").unlink(missing_ok=True)
    storage = TEST_ROOT / "storage"
    if storage.exists():
        for path in sorted(storage.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()


def test_complete_backup_is_private_readable_and_complete():
    reset_database()
    with TestClient(app) as client:
        assert client.get("/api/backups/complete").status_code == 401
        assert client.post("/api/auth/login", json={
            "email": "mark@example.com", "password": "SecureTestPassword!123",
        }).status_code == 200

        booking = client.post("/api/bookings", json={
            "brand": "wbm",
            "kind": "wedding",
            "status": "confirmed",
            "title": "Backup Test Couple",
            "client": {
                "first_name": "Backup",
                "last_name": "Tester",
                "partner_name": "Second Tester",
                "email": "backup-test@example.com",
            },
            "event_date": "2031-06-14",
            "venue_or_project": "Backup Hall",
            "package_name": "Complete collection",
            "quoted_total": 1200,
            "deposit_amount": 300,
            "deposit_paid_date": "2030-12-01",
        })
        assert booking.status_code == 201
        booking_id = booking.json()["id"]

        invoice = client.post(f"/api/bookings/{booking_id}/invoices", json={
            "total": 1200,
            "paid": 0,
            "issue_date": "2030-12-01",
            "due_date": "2031-05-14",
            "description": "Wedding photography",
        })
        assert invoice.status_code == 201
        invoice_id = invoice.json()["id"]
        assert client.post(f"/api/invoices/{invoice_id}/payments", json={
            "amount": 300,
            "paid_date": "2030-12-01",
            "payment_type": "bank_transfer",
            "reference": "BACKUP-TEST",
        }).status_code == 201
        document = client.post(
            f"/api/bookings/{booking_id}/documents?category=contract",
            files={"file": ("backup-proof.pdf", b"%PDF-1.4 backup-proof", "application/pdf")},
        )
        assert document.status_code == 201

        with SessionLocal() as db:
            db.add(SystemSetting(
                key="google_calendar_connection",
                value={"encrypted_refresh_token": "MUST-NOT-LEAVE-SERVER", "calendar_id": "primary"},
            ))
            db.commit()

        response = client.get("/api/backups/complete")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "BookingSystem2026-complete-backup-" in response.headers["content-disposition"]
        assert response.headers["cache-control"] == "no-store, max-age=0"

        archive = zipfile.ZipFile(io.BytesIO(response.content))
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert {"README.txt", "manifest.json", "database/schema.json",
                "registers/bookings.csv", "registers/invoices.csv",
                "registers/payments.csv", "checksums.sha256"}.issubset(names)
        assert any(name.startswith("uploaded-files/") and name.endswith(".pdf") for name in names)
        assert any(name.startswith("invoice-pdfs/") and name.endswith(".pdf") for name in names)
        assert any(name.startswith("invoice-pdfs/") and name.endswith("-receipt.pdf") for name in names)
        assert "program/app/main.py" in names
        assert "program/app/backup.py" in names
        assert "program/requirements.txt" in names

        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["application_build"] == "2026.08.20-dashboard-payment-total-v8.19"
        assert manifest["table_counts"]["bookings"] == 1
        assert manifest["table_counts"]["invoices"] == 1
        assert manifest["table_counts"]["payments"] == 1
        assert manifest["uploaded_file_count"] >= 1
        assert manifest["program_file_count"] > 20

        booking_export = archive.read("database/bookings.jsonl").decode("utf-8")
        assert "Backup Test Couple" in booking_export
        assert "backup-test@example.com" not in booking_export  # Stored in the clients table.
        assert "backup-test@example.com" in archive.read("database/clients.jsonl").decode("utf-8")
        assert "Backup Test Couple" in archive.read("registers/bookings.csv").decode("utf-8-sig")

        admin_export = archive.read("database/admins.jsonl").decode("utf-8")
        settings_export = archive.read("database/system_settings.jsonl").decode("utf-8")
        whole_archive = response.content
        assert "$redacted" in admin_export
        assert "SecureTestPassword!123".encode() not in whole_archive
        assert "MUST-NOT-LEAVE-SERVER".encode() not in whole_archive
        assert "Reconnect Google Calendar" in settings_export

        checksum_lines = archive.read("checksums.sha256").decode("utf-8").splitlines()
        for line in checksum_lines:
            expected, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected

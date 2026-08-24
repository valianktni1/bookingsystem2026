"""Create a private, portable BookingSystem2026 business-data backup.

The archive is intentionally generated from SQLAlchemy metadata rather than
``pg_dump`` so the same release works on PostgreSQL in production and SQLite
in the test suite.  Environment files and plaintext integration credentials
are never copied into the download.
"""

from __future__ import annotations

import csv
import enum
import hashlib
import io
import json
import os
import re
import tempfile
import threading
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import Base
from .models import (Booking, BusinessProfile, ContractAcceptance, Invoice,
                     Payment)
from .pdf import contract_acceptance_pdf, invoice_pdf


BACKUP_BUILD = "2026.08.24-visible-record-actions-v8.28.3"
BACKUP_LOCK = threading.Lock()
SENSITIVE_SETTING_KEYS = {
    "google_calendar_connection",
    "google_calendar_oauth_state",
}


class BackupBusyError(RuntimeError):
    """Raised when another complete download is already being prepared."""


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, bytes):
        return {"$type": "bytes-hex", "value": value.hex()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(value or "")).strip(" .")
    return cleaned[:140] or fallback


def _csv_bytes(fieldnames: list[str], rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if value is None else value for key, value in row.items()})
    return output.getvalue().encode("utf-8-sig")


def _zip_bytes(archive: zipfile.ZipFile, checksums: dict[str, str], name: str,
               content: bytes | str) -> None:
    raw = content.encode("utf-8") if isinstance(content, str) else content
    archive.writestr(name, raw)
    checksums[name] = hashlib.sha256(raw).hexdigest()


def _database_export(db: Session) -> tuple[dict[str, str], dict[str, int], dict[str, dict]]:
    files: dict[str, str] = {}
    counts: dict[str, int] = {}
    schema: dict[str, dict] = {}
    for table in Base.metadata.sorted_tables:
        table_rows = []
        for raw_row in db.execute(select(table)).mappings():
            row = {column.name: _json_value(raw_row[column.name]) for column in table.columns}
            if table.name == "admins" and "password_hash" in row:
                row["password_hash"] = {"$redacted": "Admin password hash is not included"}
            if table.name == "system_settings" and row.get("key") in SENSITIVE_SETTING_KEYS:
                row["value"] = {"$redacted": "Reconnect Google Calendar after a restore"}
            table_rows.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
        counts[table.name] = len(table_rows)
        files[f"database/{table.name}.jsonl"] = "\n".join(table_rows) + ("\n" if table_rows else "")
        schema[table.name] = {
            "columns": [
                {
                    "name": column.name,
                    "type": str(column.type),
                    "nullable": bool(column.nullable),
                    "primary_key": bool(column.primary_key),
                }
                for column in table.columns
            ],
            "foreign_keys": [
                {"column": fk.parent.name, "target": str(fk.target_fullname)}
                for fk in table.foreign_keys
            ],
        }
    return files, counts, schema


def _readable_registers(db: Session) -> dict[str, bytes]:
    bookings = db.scalars(
        select(Booking).options(selectinload(Booking.client)).order_by(Booking.created_at)
    ).all()
    invoices = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.booking).selectinload(Booking.client))
        .order_by(Invoice.created_at)
    ).all()
    payments = db.scalars(
        select(Payment).options(selectinload(Payment.invoice)).order_by(Payment.created_at)
    ).all()
    return {
        "registers/bookings.csv": _csv_bytes(
            ["id", "brand", "kind", "status", "couple_or_client", "email", "phone",
             "event_date", "venue_or_project", "package_name", "quoted_total",
             "deposit_amount", "deposit_paid_date", "balance_due_date", "legacy_source",
             "is_test", "created_at", "updated_at", "archived_at"],
            [{
                "id": item.id,
                "brand": item.brand.value,
                "kind": item.kind.value,
                "status": item.status.value,
                "couple_or_client": item.title,
                "email": item.client.email,
                "phone": item.client.phone,
                "event_date": item.event_date,
                "venue_or_project": item.venue_or_project,
                "package_name": item.package_name,
                "quoted_total": item.quoted_total,
                "deposit_amount": item.deposit_amount,
                "deposit_paid_date": item.deposit_paid_date,
                "balance_due_date": item.balance_due_date,
                "legacy_source": item.legacy_source,
                "is_test": item.is_test,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "archived_at": item.archived_at,
            } for item in bookings],
        ),
        "registers/invoices.csv": _csv_bytes(
            ["id", "number", "brand", "booking_id", "client", "issue_date", "due_date",
             "total", "paid", "balance", "status", "description", "legacy_number",
             "legacy_source", "created_at"],
            [{
                "id": item.id,
                "number": item.number,
                "brand": item.brand.value,
                "booking_id": item.booking_id,
                "client": item.booking.title,
                "issue_date": item.issue_date,
                "due_date": item.due_date,
                "total": item.total,
                "paid": item.paid,
                "balance": Decimal(str(item.total or 0)) - Decimal(str(item.paid or 0)),
                "status": item.status,
                "description": item.description,
                "legacy_number": item.legacy_number,
                "legacy_source": item.legacy_source,
                "created_at": item.created_at,
            } for item in invoices],
        ),
        "registers/payments.csv": _csv_bytes(
            ["id", "invoice_id", "invoice_number", "amount", "paid_date", "payment_type",
             "reference", "notes", "legacy_source", "legacy_reference", "created_at"],
            [{
                "id": item.id,
                "invoice_id": item.invoice_id,
                "invoice_number": item.invoice.number,
                "amount": item.amount,
                "paid_date": item.paid_date,
                "payment_type": item.payment_type,
                "reference": item.reference,
                "notes": item.notes,
                "legacy_source": item.legacy_source,
                "legacy_reference": item.legacy_reference,
                "created_at": item.created_at,
            } for item in payments],
        ),
    }


def _generated_pdfs(db: Session) -> tuple[dict[str, bytes], list[str]]:
    files: dict[str, bytes] = {}
    warnings: list[str] = []
    profiles = {profile.brand: profile for profile in db.scalars(select(BusinessProfile)).all()}
    invoices = db.scalars(
        select(Invoice).options(
            selectinload(Invoice.booking).selectinload(Booking.client),
            selectinload(Invoice.payments),
        ).order_by(Invoice.number)
    ).all()
    for item in invoices:
        profile = profiles.get(item.brand)
        if not profile:
            warnings.append(f"Invoice {item.number}: business profile missing; PDF not generated")
            continue
        name = _safe_name(item.number, item.id)
        try:
            files[f"invoice-pdfs/{name}.pdf"] = invoice_pdf(item, profile)
            if Decimal(str(item.paid or 0)) > 0:
                files[f"invoice-pdfs/{name}-receipt.pdf"] = invoice_pdf(item, profile, receipt=True)
        except Exception as exc:  # A broken historic record must not prevent the main backup.
            warnings.append(f"Invoice {item.number}: PDF not generated ({type(exc).__name__})")

    acceptances = db.scalars(
        select(ContractAcceptance)
        .options(selectinload(ContractAcceptance.booking))
        .order_by(ContractAcceptance.accepted_at)
    ).all()
    for item in acceptances:
        profile = profiles.get(item.booking.brand)
        if not profile:
            warnings.append(f"Agreement {item.id}: business profile missing; PDF not generated")
            continue
        couple = _safe_name(item.booking.title, item.booking_id)
        try:
            files[f"signed-agreements/{couple}-{item.id[:8]}.pdf"] = contract_acceptance_pdf(item, profile)
        except Exception as exc:
            warnings.append(f"Agreement {item.id}: PDF not generated ({type(exc).__name__})")
    return files, warnings


def _program_snapshot() -> dict[str, bytes]:
    """Include the running source tree; environment values live outside it."""
    files: dict[str, bytes] = {}
    app_root = Path(__file__).resolve().parent
    for path in sorted(app_root.rglob("*")):
        if (path.is_symlink() or not path.is_file() or path.suffix in {".pyc", ".pyo"}
                or "__pycache__" in path.parts):
            continue
        relative = path.relative_to(app_root).as_posix()
        files[f"program/app/{relative}"] = path.read_bytes()
    requirements = app_root.parent / "requirements.txt"
    if requirements.is_file():
        files["program/requirements.txt"] = requirements.read_bytes()
    return files


def create_complete_backup(
    db: Session,
    progress: Callable[[int, str], None] | None = None,
) -> tuple[Path, str, dict]:
    """Create a dated ZIP and return its temporary path, filename and manifest."""
    def report(percent: int, message: str) -> None:
        if progress:
            progress(percent, message)

    if not BACKUP_LOCK.acquire(blocking=False):
        raise BackupBusyError("A complete backup is already being prepared")
    try:
        report(3, "Reading the complete database")
        created_at = datetime.now(timezone.utc)
        stamp = created_at.astimezone().strftime("%Y%m%d-%H%M%S")
        filename = f"BookingSystem2026-complete-backup-{stamp}.zip"
        descriptor, temp_name = tempfile.mkstemp(prefix="bookingsystem2026-backup-", suffix=".zip")
        os.close(descriptor)
        target = Path(temp_name)
        checksums: dict[str, str] = {}
        warnings: list[str] = []
        try:
            database_files, table_counts, schema = _database_export(db)
            report(20, "Preparing readable booking and payment registers")
            registers = _readable_registers(db)
            report(32, "Creating invoice, receipt and agreement PDFs")
            generated_pdfs, pdf_warnings = _generated_pdfs(db)
            report(55, "Copying the running program safely")
            program_files = _program_snapshot()
            warnings.extend(pdf_warnings)

            storage_root = get_settings().storage_root
            stored_files: list[tuple[Path, str]] = []
            report(62, "Finding uploaded client documents")
            if storage_root.exists():
                resolved_root = storage_root.resolve()
                for path in sorted(storage_root.rglob("*")):
                    if path.is_symlink() or not path.is_file():
                        continue
                    resolved = path.resolve()
                    if not resolved.is_relative_to(resolved_root):
                        warnings.append(f"Skipped unsafe stored path: {path.name}")
                        continue
                    relative = resolved.relative_to(resolved_root).as_posix()
                    stored_files.append((resolved, f"uploaded-files/{relative}"))

            manifest = {
                "format": "BookingSystem2026 complete business-data backup",
                "format_version": 1,
                "application_build": BACKUP_BUILD,
                "created_at_utc": created_at.isoformat(),
                "database_dialect": db.bind.dialect.name if db.bind is not None else "unknown",
                "table_counts": table_counts,
                "database_row_count": sum(table_counts.values()),
                "uploaded_file_count": len(stored_files),
                "generated_pdf_count": len(generated_pdfs),
                "program_file_count": len(program_files),
                "security": {
                    "environment_file_included": False,
                    "plaintext_passwords_included": False,
                    "google_or_smtp_credentials_included": False,
                    "admin_password_hash_redacted": True,
                    "google_oauth_connection_redacted": True,
                },
                "warnings": warnings,
            }
            readme = (
                "BOOKINGSYSTEM2026 COMPLETE BACKUP\n"
                "=================================\n\n"
                f"Created: {created_at.isoformat()}\n"
                f"Build: {BACKUP_BUILD}\n\n"
                "This private archive contains the complete business-data snapshot: every database\n"
                "table, uploaded client document, readable booking/invoice/payment registers,\n"
                "invoice PDFs, receipts and signed-agreement PDFs that could be generated. It also\n"
                "contains the running application source and dependency list under program/.\n\n"
                "SECURITY\n"
                "--------\n"
                "The archive contains confidential client and financial information. Store it safely.\n"
                "The .env file, plaintext passwords, SMTP credentials, Google Client Secret and Google\n"
                "refresh token are not included. The admin password must be reset and Google Calendar\n"
                "reconnected after a full restore.\n\n"
                "RESTORE\n"
                "-------\n"
                "Keep this ZIP unchanged. The database/*.jsonl files are a typed, lossless logical\n"
                "snapshot; schema.json records the columns and relationships. Restoration should be\n"
                "performed into a fresh BookingSystem2026 installation by a competent administrator.\n"
                "Do not import individual JSONL files into the live system by hand.\n"
            )

            report(70, "Building and checking the private ZIP")
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as archive:
                _zip_bytes(archive, checksums, "README.txt", readme)
                _zip_bytes(archive, checksums, "manifest.json",
                           json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
                _zip_bytes(archive, checksums, "database/schema.json",
                           json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True))
                for name, content in database_files.items():
                    _zip_bytes(archive, checksums, name, content)
                for name, content in registers.items():
                    _zip_bytes(archive, checksums, name, content)
                for name, content in generated_pdfs.items():
                    _zip_bytes(archive, checksums, name, content)
                for name, content in program_files.items():
                    _zip_bytes(archive, checksums, name, content)
                uploaded_total = max(1, len(stored_files))
                for position, (source, archive_name) in enumerate(stored_files, start=1):
                    digest = hashlib.sha256()
                    with source.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    archive.write(source, archive_name)
                    checksums[archive_name] = digest.hexdigest()
                    report(70 + min(24, int(position / uploaded_total * 24)),
                           f"Adding uploaded documents ({position} of {len(stored_files)})")
                checksum_text = "".join(
                    f"{digest}  {name}\n" for name, digest in sorted(checksums.items())
                )
                archive.writestr("checksums.sha256", checksum_text.encode("utf-8"))
            report(100, "Backup ready to download")
            return target, filename, manifest
        except Exception:
            target.unlink(missing_ok=True)
            raise
    finally:
        BACKUP_LOCK.release()

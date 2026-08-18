"""Guarded one-off chronological renumbering for Weddings By Mark invoices.

The booking database remains the source of truth.  This command never sends
email, creates portal links, runs reminders, or contacts the accounts system.
It must be run while the normal booking app container is stopped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import SessionLocal
from .models import AuditLog, Booking, Brand, Invoice, InvoiceCounter, Payment, SystemSetting


CONFIRMATION = "RENUMBER ALL WBM INVOICES"
MIGRATION_KEY = "wbm_chronological_invoice_renumber_v1"


def _positive_payment_date(invoice: Invoice) -> date | None:
    dates = [payment.paid_date for payment in invoice.payments if Decimal(payment.amount or 0) > 0]
    return min(dates) if dates else None


def _sort_key(invoice: Invoice) -> tuple:
    payment_date = _positive_payment_date(invoice)
    effective_date = payment_date or invoice.issue_date
    return (
        effective_date,
        0 if payment_date else 1,
        invoice.issue_date,
        invoice.created_at.isoformat() if invoice.created_at else "",
        invoice.number,
        invoice.id,
    )


def build_plan(invoices: list[Invoice], *, start: int = 2000, prefix: str = "WBM") -> list[dict]:
    plan = []
    for position, invoice in enumerate(sorted(invoices, key=_sort_key), start=1):
        payment_date = _positive_payment_date(invoice)
        sequence = start + position
        plan.append({
            "invoice_id": invoice.id,
            "booking_id": invoice.booking_id,
            "couple": invoice.booking.title if invoice.booking else "",
            "old_number": invoice.number,
            "new_number": f"{prefix}{sequence:05d}",
            "new_sequence": sequence,
            "legacy_number": invoice.legacy_number,
            "issue_date": invoice.issue_date.isoformat(),
            "first_positive_payment_date": payment_date.isoformat() if payment_date else None,
            "ordering_date": (payment_date or invoice.issue_date).isoformat(),
            "ordering_source": "first_positive_payment" if payment_date else "issue_date_fallback",
            "status": invoice.status,
        })
    return plan


def plan_digest(plan: list[dict]) -> str:
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_invoices(db: Session, *, lock: bool = False) -> list[Invoice]:
    statement = (
        select(Invoice)
        .options(selectinload(Invoice.booking), selectinload(Invoice.payments))
        .where(Invoice.brand == Brand.WBM)
    )
    if lock:
        statement = statement.with_for_update()
    return list(db.scalars(statement).unique().all())


def _write_plan(plan: list[dict], digest: str, *, suffix: str) -> tuple[Path, Path]:
    settings = get_settings()
    folder = settings.storage_root / "migrations" / "invoice-renumber"
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"wbm-chronological-invoice-renumber-{suffix}-{timestamp}-{digest[:12]}"
    json_path = folder / f"{stem}.json"
    csv_path = folder / f"{stem}.csv"
    json_path.write_text(json.dumps({
        "migration": MIGRATION_KEY,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "digest": digest,
        "count": len(plan),
        "first_number": plan[0]["new_number"] if plan else None,
        "last_number": plan[-1]["new_number"] if plan else None,
        "records": plan,
    }, indent=2), encoding="utf-8")
    fields = list(plan[0].keys()) if plan else ["invoice_id", "old_number", "new_number"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(plan)
    return json_path, csv_path


def _validate_targets(db: Session, plan: list[dict], scoped_ids: set[str]) -> None:
    targets = [row["new_number"] for row in plan]
    conflicts = list(db.scalars(
        select(Invoice).where(Invoice.number.in_(targets), ~Invoice.id.in_(scoped_ids))
    ).all()) if targets else []
    if conflicts:
        numbers = ", ".join(sorted(row.number for row in conflicts)[:10])
        raise RuntimeError(f"Target invoice numbers are already used outside WBM: {numbers}")


def apply_plan(*, expected_digest: str, confirmation: str) -> tuple[list[dict], str, Path, Path]:
    if confirmation != CONFIRMATION:
        raise RuntimeError(f'Type --confirmation "{CONFIRMATION}" exactly')
    settings = get_settings()
    with SessionLocal() as db:
        with db.begin():
            invoices = _load_invoices(db, lock=True)
            plan = build_plan(invoices, start=settings.invoice_start)
            digest = plan_digest(plan)
            if digest != expected_digest:
                raise RuntimeError(
                    "The database changed after the dry run. Run --dry-run again and use its new digest."
                )
            if plan and not any(row["old_number"] != row["new_number"] for row in plan):
                raise RuntimeError("All WBM invoices are already in the chronological sequence.")
            previous = db.get(SystemSetting, MIGRATION_KEY)
            if previous and previous.value.get("digest") == digest:
                raise RuntimeError("This exact chronological renumbering has already been applied.")
            scoped_ids = {row["invoice_id"] for row in plan}
            _validate_targets(db, plan, scoped_ids)
            by_id = {invoice.id: invoice for invoice in invoices}

            # Vacate every old number first so swaps cannot violate the unique index.
            for invoice in invoices:
                invoice.number = f"M{invoice.id.replace('-', '')[:28]}"
                invoice.sequence = -abs(invoice.sequence or 1)
            db.flush()

            changed = 0
            for row in plan:
                invoice = by_id[row["invoice_id"]]
                if row["old_number"] != row["new_number"]:
                    changed += 1
                invoice.number = row["new_number"]
                invoice.sequence = row["new_sequence"]

            final_sequence = settings.invoice_start + len(plan)
            counter = db.get(InvoiceCounter, "brand:wbm")
            if counter:
                counter.value = final_sequence
            else:
                db.add(InvoiceCounter(key="brand:wbm", value=final_sequence))

            marker_value = {
                "digest": digest,
                "count": len(plan),
                "changed": changed,
                "first_number": plan[0]["new_number"] if plan else None,
                "last_number": plan[-1]["new_number"] if plan else None,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "emails_sent": 0,
                "accounts_contacted": False,
            }
            if previous:
                previous.value = marker_value
                previous.updated_at = datetime.now(timezone.utc)
            else:
                db.add(SystemSetting(key=MIGRATION_KEY, value=marker_value))
            db.add(AuditLog(
                action="chronological_invoice_renumber",
                entity_type="invoice_batch",
                entity_id=MIGRATION_KEY,
                details=marker_value,
            ))
        json_path, csv_path = _write_plan(plan, digest, suffix="applied")
        return plan, digest, json_path, csv_path


def _print_summary(plan: list[dict], digest: str, json_path: Path, csv_path: Path, *, applied: bool) -> None:
    changed = sum(row["old_number"] != row["new_number"] for row in plan)
    print("BookingSystem2026 chronological WBM invoice renumber")
    print("Client emails/reminders/portal links: NOT TOUCHED")
    print("Accounts system: NOT CONTACTED")
    print(f"Invoices: {len(plan)} total, {changed} numbers changing")
    if plan:
        print(f"New sequence: {plan[0]['new_number']} to {plan[-1]['new_number']}")
    print(f"Digest: {digest}")
    print(f"JSON audit: {json_path}")
    print(f"CSV audit:  {csv_path}")
    if applied:
        print("\nRENUMBER COMPLETE - issue dates, payments, totals and statuses were preserved.")
        print("Leave automatic accounts sync off; use the manual sync after both apps are upgraded.")
    else:
        print("\nDRY RUN ONLY - the database was not changed.")
        print("Apply only after checking the CSV and taking both database backups:")
        print("python -m app.invoice_renumber --apply \\")
        print(f"  --expected-digest {digest} \\")
        print(f'  --confirmation "{CONFIRMATION}"')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-digest")
    parser.add_argument("--confirmation")
    args = parser.parse_args()
    try:
        if args.dry_run:
            with SessionLocal() as db:
                plan = build_plan(_load_invoices(db), start=get_settings().invoice_start)
            digest = plan_digest(plan)
            json_path, csv_path = _write_plan(plan, digest, suffix="preview")
            _print_summary(plan, digest, json_path, csv_path, applied=False)
            return 0
        if not args.expected_digest:
            raise RuntimeError("--expected-digest from the dry run is required")
        plan, digest, json_path, csv_path = apply_plan(
            expected_digest=args.expected_digest,
            confirmation=args.confirmation or "",
        )
        _print_summary(plan, digest, json_path, csv_path, applied=True)
        return 0
    except Exception as exc:
        print(f"STOPPED SAFELY: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""An opt-in, read-only WBM summary for Mark's private dashboard."""
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

from fastapi import Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .business_time import business_today
from .config import get_settings
from .database import get_db
from .models import Booking, Brand, RecordKind, RecordStatus

QUEUE_KEYS = ("new_enquiries", "quotes_waiting", "accepted_payment", "forms_waiting",
              "agreements_waiting", "overdue_payments", "payments_due")


def build_overview(db: Session, workflow_queues):
    eligible = (Booking.brand == Brand.WBM, Booking.kind == RecordKind.WEDDING,
                Booking.archived_at.is_(None), Booking.is_test.is_(False),
                Booking.status != RecordStatus.CANCELLED)
    live_ids = set(db.scalars(select(Booking.id).where(*eligible)).all())
    original = workflow_queues(db=db, _=None)["queues"]
    groups = {}
    for key in QUEUE_KEYS:
        rows = [row for row in original[key] if row["booking_id"] in live_ids]
        section = "payments" if key in ("accepted_payment", "overdue_payments", "payments_due") else "journey"
        items = [{
            "title": row["title"], "event_date": row["event_date"], "due_date": row["due_date"],
            "amount_pence": int(Decimal(str(row["amount"])) * 100) if row["amount"] is not None else None,
            "path": f"/bookings/{quote(row['booking_id'], safe='')}/{section}",
        } for row in rows]
        groups[key] = {"count": len(items), "items": items[:5],
                       "total_amount_pence": sum(row["amount_pence"] or 0 for row in items)}
    weddings = db.scalars(select(Booking).where(
        *eligible, Booking.status.in_((RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS)),
        Booking.event_date >= business_today(),
    ).order_by(Booking.event_date, Booking.id).limit(5)).all()
    return {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "business_date": business_today().isoformat(), "currency": "GBP", "queues": groups,
        "payment_amount_basis": "outstanding_invoice_balance",
        "upcoming_weddings": [{"title": row.title, "event_date": row.event_date.isoformat(),
                               "venue": row.venue_or_project,
                               "path": f"/bookings/{quote(row.id, safe='')}/overview"} for row in weddings],
    }


def register_control_centre_routes(app, workflow_queues):
    @app.get("/api/integrations/control-centre/overview")
    def overview(response: Response, x_control_centre_key: str | None = Header(default=None),
                 db: Session = Depends(get_db)):
        response.headers["Cache-Control"] = "private, no-store"
        settings = get_settings()
        expected = settings.control_centre_key or ""
        if not settings.control_centre_enabled or len(expected) < 32:
            raise HTTPException(503, "Control Centre connection is disabled", headers={"Cache-Control":"no-store"})
        if not x_control_centre_key or not secrets.compare_digest(x_control_centre_key.encode("utf-8"), expected.encode("utf-8")):
            raise HTTPException(401, "Control Centre key was not accepted", headers={"Cache-Control":"no-store"})
        return build_overview(db, workflow_queues)

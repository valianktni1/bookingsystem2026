"""Private unavailable-date management for Weddings By Mark (V8.35)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .google_calendar import sync_date_block_calendar_safely
from .models import (Admin, AuditLog, Booking, Brand, DateBlock, RecordKind,
                     RecordStatus)
from .security import current_admin


class DateBlockIn(BaseModel):
    start_date: date
    end_date: date
    label: str = Field(default="Holiday", min_length=1, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)
    confirm_conflicts: bool = False

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_date < self.start_date:
            raise ValueError("The end date must be on or after the start date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("A blocked period cannot be longer than 367 days")
        return self


def _clean_text(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _calendar_state(block: DateBlock) -> dict:
    return dict(block.google_calendar_state or {})


def date_block_json(block: DateBlock) -> dict:
    state = _calendar_state(block)
    return {
        "id": block.id,
        "start_date": block.start_date.isoformat(),
        "end_date": block.end_date.isoformat(),
        "label": block.label,
        "notes": block.notes,
        "calendar_status": state.get("status") or "pending",
        "calendar_error": state.get("last_error"),
        "calendar_link": state.get("html_link"),
        "created_at": block.created_at,
        "updated_at": block.updated_at,
    }


def _existing_block_overlap(db: Session, start_date: date, end_date: date,
                            exclude_id: str | None = None) -> DateBlock | None:
    statement = select(DateBlock).where(
        DateBlock.deleted_at.is_(None),
        DateBlock.start_date <= end_date,
        DateBlock.end_date >= start_date,
    )
    if exclude_id:
        statement = statement.where(DateBlock.id != exclude_id)
    return db.scalar(statement.order_by(DateBlock.start_date).limit(1))


def _booking_conflicts(db: Session, start_date: date, end_date: date) -> list[dict]:
    rows = db.scalars(select(Booking).where(
        Booking.brand == Brand.WBM,
        Booking.kind == RecordKind.WEDDING,
        Booking.is_test.is_(False),
        Booking.event_date >= start_date,
        Booking.event_date <= end_date,
        Booking.status != RecordStatus.CANCELLED,
    ).order_by(Booking.event_date, Booking.title)).all()
    conflicts = []
    for booking in rows:
        if booking.archived_at is not None and booking.status in (
            RecordStatus.ENQUIRY, RecordStatus.QUOTED,
        ):
            continue
        conflicts.append({
            "booking_id": booking.id,
            "date": booking.event_date.isoformat(),
            "title": booking.title,
            "status": booking.status.value,
        })
    return conflicts


def _validate_no_block_overlap(db: Session, payload: DateBlockIn,
                               exclude_id: str | None = None) -> None:
    overlap = _existing_block_overlap(
        db, payload.start_date, payload.end_date, exclude_id=exclude_id,
    )
    if overlap:
        raise HTTPException(
            409,
            f"Those dates overlap the existing block ‘{overlap.label}’ "
            f"({overlap.start_date.strftime('%d/%m/%Y')} to "
            f"{overlap.end_date.strftime('%d/%m/%Y')}). Edit that block instead.",
        )


def _require_conflict_confirmation(db: Session, payload: DateBlockIn) -> None:
    conflicts = _booking_conflicts(db, payload.start_date, payload.end_date)
    if conflicts and not payload.confirm_conflicts:
        raise HTTPException(
            409,
            f"This period contains {len(conflicts)} existing wedding or enquiry "
            "record(s). Review the warning and confirm if you still want to block it.",
        )


def register_date_block_routes(app: FastAPI) -> None:
    @app.get("/api/date-blocks")
    def list_date_blocks(_: Admin = Depends(current_admin),
                         db: Session = Depends(get_db)):
        rows = db.scalars(select(DateBlock).where(
            DateBlock.deleted_at.is_(None),
        ).order_by(DateBlock.start_date, DateBlock.created_at)).all()
        return [date_block_json(row) for row in rows]

    @app.get("/api/date-blocks/check")
    def check_date_block(start_date: date = Query(...), end_date: date = Query(...),
                         exclude_id: str | None = Query(None),
                         _: Admin = Depends(current_admin),
                         db: Session = Depends(get_db)):
        if end_date < start_date:
            raise HTTPException(422, "The end date must be on or after the start date")
        overlap = _existing_block_overlap(db, start_date, end_date, exclude_id)
        conflicts = _booking_conflicts(db, start_date, end_date)
        return {
            "existing_block": date_block_json(overlap) if overlap else None,
            "booking_conflicts": conflicts,
            "booking_conflict_count": len(conflicts),
        }

    @app.post("/api/date-blocks", status_code=201)
    def create_date_block(payload: DateBlockIn,
                          admin: Admin = Depends(current_admin),
                          db: Session = Depends(get_db)):
        _validate_no_block_overlap(db, payload)
        _require_conflict_confirmation(db, payload)
        block = DateBlock(
            start_date=payload.start_date,
            end_date=payload.end_date,
            label=_clean_text(payload.label) or "Holiday",
            notes=_clean_text(payload.notes),
        )
        db.add(block)
        db.flush()
        db.add(AuditLog(
            action="date_block_create", entity_type="date_block", entity_id=block.id,
            details={
                "start_date": block.start_date.isoformat(),
                "end_date": block.end_date.isoformat(),
                "label": block.label,
                "admin_id": admin.id,
                "client_communications_sent": False,
            },
        ))
        db.commit()
        db.refresh(block)
        sync_date_block_calendar_safely(db, block)
        db.refresh(block)
        return date_block_json(block)

    @app.put("/api/date-blocks/{block_id}")
    def update_date_block(block_id: str, payload: DateBlockIn,
                          admin: Admin = Depends(current_admin),
                          db: Session = Depends(get_db)):
        block = db.get(DateBlock, block_id)
        if not block or block.deleted_at is not None:
            raise HTTPException(404, "Date block not found")
        _validate_no_block_overlap(db, payload, exclude_id=block.id)
        _require_conflict_confirmation(db, payload)
        before = {
            "start_date": block.start_date.isoformat(),
            "end_date": block.end_date.isoformat(),
            "label": block.label,
            "notes": block.notes,
        }
        block.start_date = payload.start_date
        block.end_date = payload.end_date
        block.label = _clean_text(payload.label) or "Holiday"
        block.notes = _clean_text(payload.notes)
        block.updated_at = datetime.now(timezone.utc)
        db.add(AuditLog(
            action="date_block_update", entity_type="date_block", entity_id=block.id,
            details={
                "before": before,
                "after": {
                    "start_date": block.start_date.isoformat(),
                    "end_date": block.end_date.isoformat(),
                    "label": block.label,
                    "notes": block.notes,
                },
                "admin_id": admin.id,
                "client_communications_sent": False,
            },
        ))
        db.commit()
        sync_date_block_calendar_safely(db, block)
        db.refresh(block)
        return date_block_json(block)

    @app.delete("/api/date-blocks/{block_id}")
    def delete_date_block(block_id: str, admin: Admin = Depends(current_admin),
                          db: Session = Depends(get_db)):
        block = db.get(DateBlock, block_id)
        if not block or block.deleted_at is not None:
            raise HTTPException(404, "Date block not found")
        block.deleted_at = datetime.now(timezone.utc)
        block.updated_at = block.deleted_at
        db.add(AuditLog(
            action="date_block_delete", entity_type="date_block", entity_id=block.id,
            details={
                "start_date": block.start_date.isoformat(),
                "end_date": block.end_date.isoformat(),
                "label": block.label,
                "admin_id": admin.id,
                "client_communications_sent": False,
            },
        ))
        db.commit()
        sync_date_block_calendar_safely(db, block)
        db.refresh(block)
        return {
            "ok": True,
            "message": "Blocked period removed. No client email was sent.",
            "calendar_status": _calendar_state(block).get("status") or "removed",
        }

    @app.post("/api/date-blocks/{block_id}/google-calendar-sync")
    def retry_date_block_calendar(block_id: str,
                                  _: Admin = Depends(current_admin),
                                  db: Session = Depends(get_db)):
        block = db.get(DateBlock, block_id)
        if not block:
            raise HTTPException(404, "Date block not found")
        return sync_date_block_calendar_safely(db, block)

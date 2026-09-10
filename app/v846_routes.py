"""V8.46 protected after-wedding workflow.

The complete delivery checklist is retained inside ``Booking.workflow_state``.
This deliberately avoids a database migration and never rewrites invoices,
payments, accepted quote snapshots, agreements or client documents.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .models import Admin, Booking, Brand, Invoice, Quote, RecordKind, RecordStatus
from .security import current_admin
from .services import audit


class AfterWeddingUpdateIn(BaseModel):
    photos_status: Literal["pending", "delivered"]
    photos_delivered_on: date | None = None
    gallery_url: str | None = Field(default=None, max_length=2000)
    video_status: Literal["not_required", "pending", "delivered"]
    video_delivered_on: date | None = None
    video_url: str | None = Field(default=None, max_length=2000)
    album_status: Literal[
        "not_required", "awaiting_selection", "designing", "ordered", "delivered"
    ]
    album_delivered_on: date | None = None
    album_notes: str | None = Field(default=None, max_length=2000)


ALBUM_LABELS = {
    "not_required": "Not required",
    "awaiting_selection": "Awaiting image choices",
    "designing": "Designing album",
    "ordered": "Ordered from supplier",
    "delivered": "Delivered",
}


def _clean_url(value: str | None, label: str) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    if not cleaned.lower().startswith(("https://", "http://")):
        raise HTTPException(422, f"{label} must begin with https:// or http://")
    return cleaned


def _accepted_quote(db: Session, booking: Booking) -> Quote | None:
    for quote in getattr(booking, "quotes", []) or []:
        if quote.status == "accepted":
            return quote
    return db.scalar(select(Quote).where(
        Quote.booking_id == booking.id,
        Quote.status == "accepted",
    ).order_by(Quote.accepted_at.desc()).limit(1))


def _initial_requirements(db: Session, booking: Booking) -> dict[str, bool]:
    quote = _accepted_quote(db, booking)
    parts = [booking.package_name or ""]
    for item in (quote.line_items if quote else []) or []:
        if isinstance(item, dict):
            parts.extend((str(item.get("name") or ""), str(item.get("description") or "")))
    evidence = " ".join(parts).lower()
    video = any(word in evidence for word in ("video", "film", "videograph"))
    album = "album" in evidence
    return {"photos": True, "video": video, "album": album}


def _status_date(raw: dict, key: str) -> str | None:
    value = raw.get(key)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            return None
    return None


def after_wedding_state(db: Session, booking: Booking) -> dict:
    raw = dict((booking.workflow_state or {}).get("after_wedding") or {})
    inferred = _initial_requirements(db, booking)
    photos = dict(raw.get("photos") or {})
    video = dict(raw.get("video") or {})
    album = dict(raw.get("album") or {})
    review = dict(raw.get("review_request") or {})

    photos_status = str(photos.get("status") or "pending")
    if photos_status not in {"pending", "delivered"}:
        photos_status = "pending"
    video_status = str(video.get("status") or ("pending" if inferred["video"] else "not_required"))
    if video_status not in {"not_required", "pending", "delivered"}:
        video_status = "pending" if inferred["video"] else "not_required"
    album_status = str(album.get("status") or (
        "awaiting_selection" if inferred["album"] else "not_required"
    ))
    if album_status not in ALBUM_LABELS:
        album_status = "awaiting_selection" if inferred["album"] else "not_required"

    return {
        "photos": {
            "status": photos_status,
            "delivered_on": _status_date(photos, "delivered_on"),
            "gallery_url": str(photos.get("gallery_url") or "").strip() or None,
        },
        "video": {
            "status": video_status,
            "delivered_on": _status_date(video, "delivered_on"),
            "video_url": str(video.get("video_url") or "").strip() or None,
        },
        "album": {
            "status": album_status,
            "status_label": ALBUM_LABELS[album_status],
            "delivered_on": _status_date(album, "delivered_on"),
            "notes": str(album.get("notes") or "").strip() or None,
        },
        "review_request": {
            "status": "sent" if review.get("sent_at") else "not_requested",
            "sent_at": review.get("sent_at"),
            "subject": review.get("subject"),
        },
        "updated_at": raw.get("updated_at"),
        "updated_by": raw.get("updated_by"),
    }


def after_wedding_readiness(db: Session, booking: Booking) -> dict:
    state = after_wedding_state(db, booking)
    outstanding = sum((
        max(Decimal(invoice.total or 0) - Decimal(invoice.paid or 0), Decimal("0"))
        for invoice in booking.invoices
        if invoice.status not in ("paid", "void", "cancelled")
    ), Decimal("0"))
    wedding_has_passed = bool(booking.event_date and booking.event_date <= date.today())
    checks = [
        {
            "key": "photos",
            "label": "Photographs delivered",
            "complete": state["photos"]["status"] == "delivered",
        },
        {
            "key": "video",
            "label": "Video delivered or not required",
            "complete": state["video"]["status"] in {"delivered", "not_required"},
        },
        {
            "key": "album",
            "label": "Album delivered or not required",
            "complete": state["album"]["status"] in {"delivered", "not_required"},
        },
        {
            "key": "account",
            "label": "Account balance clear",
            "complete": outstanding == 0,
        },
    ]
    blockers = [row["label"] for row in checks if not row["complete"]]
    if not wedding_has_passed:
        blockers.insert(0, "Wedding date has not passed")
    ready = not blockers
    if booking.status == RecordStatus.COMPLETED:
        ready = True
    return {
        "ready_to_complete": ready,
        "wedding_has_passed": wedding_has_passed,
        "outstanding_balance": float(outstanding),
        "checks": checks,
        "completed_count": sum(1 for row in checks if row["complete"]),
        "check_count": len(checks),
        "blockers": blockers,
    }


def after_wedding_json(db: Session, booking: Booking) -> dict:
    eligible = bool(
        booking.brand == Brand.WBM
        and booking.kind == RecordKind.WEDDING
        and booking.status not in (RecordStatus.ENQUIRY, RecordStatus.QUOTED, RecordStatus.CANCELLED)
    )
    return {
        "booking_id": booking.id,
        "eligible": eligible,
        "native_booking": booking.legacy_source != "studio_ninja",
        "manual_only": bool(booking.legacy_source == "studio_ninja" or booking.automation_suppressed),
        "completed": booking.status == RecordStatus.COMPLETED,
        "state": after_wedding_state(db, booking),
        "readiness": after_wedding_readiness(db, booking),
    }


def register_v846_routes(app: FastAPI) -> None:
    def load_booking(db: Session, booking_id: str) -> Booking:
        booking = db.scalar(select(Booking).options(
            selectinload(Booking.quotes),
            selectinload(Booking.invoices).selectinload(Invoice.payments),
        ).where(Booking.id == booking_id))
        if not booking:
            raise HTTPException(404, "Wedding booking not found")
        return booking

    @app.get("/api/bookings/{booking_id}/after-wedding")
    def get_after_wedding(
        booking_id: str,
        _: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        return after_wedding_json(db, load_booking(db, booking_id))

    @app.put("/api/bookings/{booking_id}/after-wedding")
    def update_after_wedding(
        booking_id: str,
        payload: AfterWeddingUpdateIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = load_booking(db, booking_id)
        if booking.brand != Brand.WBM or booking.kind != RecordKind.WEDDING:
            raise HTTPException(409, "After-wedding tracking is only available for Weddings By Mark weddings")
        if booking.status in (RecordStatus.ENQUIRY, RecordStatus.QUOTED):
            raise HTTPException(409, "This wedding has not reached the booked stage")
        if booking.status == RecordStatus.CANCELLED:
            raise HTTPException(409, "Reopen this cancelled wedding before changing delivery progress")

        now = datetime.now(timezone.utc)
        existing = after_wedding_state(db, booking)
        photos_date = payload.photos_delivered_on
        if payload.photos_status == "delivered" and not photos_date:
            photos_date = date.today()
        video_date = payload.video_delivered_on
        if payload.video_status == "delivered" and not video_date:
            video_date = date.today()
        album_date = payload.album_delivered_on
        if payload.album_status == "delivered" and not album_date:
            album_date = date.today()

        stored = {
            "photos": {
                "status": payload.photos_status,
                "delivered_on": photos_date.isoformat() if photos_date else None,
                "gallery_url": _clean_url(payload.gallery_url, "Gallery link"),
            },
            "video": {
                "status": payload.video_status,
                "delivered_on": video_date.isoformat() if video_date else None,
                "video_url": _clean_url(payload.video_url, "Video link"),
            },
            "album": {
                "status": payload.album_status,
                "delivered_on": album_date.isoformat() if album_date else None,
                "notes": str(payload.album_notes or "").strip() or None,
            },
            "review_request": existing["review_request"],
            "updated_at": now.isoformat(),
            "updated_by": admin.email,
        }
        # ``status`` is derived from sent_at, so keep only the durable evidence.
        stored["review_request"].pop("status", None)
        workflow = dict(booking.workflow_state or {})
        workflow["after_wedding"] = stored
        booking.workflow_state = workflow
        audit(db, "update_after_wedding_workflow", "booking", booking.id, {
            "photos_status": payload.photos_status,
            "video_status": payload.video_status,
            "album_status": payload.album_status,
            "client_email_sent": False,
            "financial_records_changed": False,
        })
        db.commit()
        return after_wedding_json(db, booking)

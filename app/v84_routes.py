"""Version 8.4 migration-safety and wedding-journey controls."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Admin, Booking, FormSubmission, RecordKind
from .security import current_admin
from .services import audit


class AutomationControlIn(BaseModel):
    enabled: bool
    reason: str = Field(min_length=3, max_length=1000)
    confirmation: str | None = Field(default=None, max_length=100)


class FinalDetailsControlIn(BaseModel):
    unlocked: bool
    reason: str = Field(min_length=3, max_length=1000)


def automations_allowed(booking: Booking) -> bool:
    return not bool(booking.automation_suppressed)


def final_details_unlocked(db: Session, booking: Booking) -> bool:
    if booking.kind != RecordKind.WEDDING:
        return True
    if db.scalar(select(FormSubmission.id).where(
        FormSubmission.booking_id == booking.id,
        FormSubmission.form_type == "final_questionnaire",
    ).limit(1)):
        return True
    workflow = dict(booking.workflow_state or {})
    if workflow.get("final_details_manual_unlock") is True:
        return True
    if not booking.event_date:
        return False
    return (booking.event_date - date.today()).days <= 30


def register_v84_routes(app: FastAPI) -> None:
    @app.post("/api/bookings/{booking_id}/automations")
    def control_booking_automations(
        booking_id: str,
        payload: AutomationControlIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = db.get(Booking, booking_id)
        if not booking:
            raise HTTPException(404, "Record not found")
        if payload.enabled and booking.legacy_source == "studio_ninja":
            raise HTTPException(
                409,
                "Studio Ninja general automation remains permanently blocked. "
                "The sole exception is the protected 30-day Final Wedding Timings invitation "
                "for weddings after 20 October 2026; use a protected one-off link or email "
                "for anything else.",
            )
        if payload.enabled and payload.confirmation != "ACTIVATE CLIENT EMAILS":
            raise HTTPException(422, "Type ACTIVATE CLIENT EMAILS exactly to confirm")
        booking.automation_suppressed = not payload.enabled
        workflow = dict(booking.workflow_state or {})
        history = list(workflow.get("automation_history") or [])
        history.append({
            "enabled": payload.enabled,
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "changed_by": admin.email,
            "reason": payload.reason.strip(),
        })
        workflow["automation_history"] = history[-50:]
        booking.workflow_state = workflow
        audit(db, "activate_automations" if payload.enabled else "pause_automations",
              "booking", booking.id, {"reason": payload.reason.strip(), "admin": admin.email})
        db.commit()
        return {
            "ok": True,
            "automation_suppressed": booking.automation_suppressed,
            "message": ("Client emails and reminders are active"
                        if payload.enabled else "Client emails and reminders are paused"),
        }

    @app.post("/api/bookings/{booking_id}/final-details")
    def control_final_details(
        booking_id: str,
        payload: FinalDetailsControlIn,
        admin: Admin = Depends(current_admin),
        db: Session = Depends(get_db),
    ):
        booking = db.get(Booking, booking_id)
        if not booking:
            raise HTTPException(404, "Record not found")
        if booking.kind != RecordKind.WEDDING:
            raise HTTPException(422, "Final wedding details only apply to wedding bookings")
        workflow = dict(booking.workflow_state or {})
        workflow["final_details_manual_unlock"] = payload.unlocked
        workflow["final_details_control"] = {
            "unlocked": payload.unlocked,
            "changed_at": datetime.now(timezone.utc).isoformat(),
            "changed_by": admin.email,
            "reason": payload.reason.strip(),
        }
        booking.workflow_state = workflow
        audit(db, "unlock_final_details" if payload.unlocked else "use_scheduled_final_details",
              "booking", booking.id, {"reason": payload.reason.strip(), "admin": admin.email})
        db.commit()
        return {
            "ok": True,
            "final_details_unlocked": final_details_unlocked(db, booking),
            "manual_unlock": payload.unlocked,
        }

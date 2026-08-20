"""Final wedding timings validation, coverage calculation and safety rules.

The feature deliberately stores answers in the existing ``form_submissions``
table.  That keeps deployment additive and avoids rewriting any booking,
invoice, contract or imported Studio Ninja data.
"""

from __future__ import annotations

import math
import re
from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Brand, Booking, FormSubmission, Quote, RecordKind, RecordStatus


FORM_TYPE = "final_timings"
FORM_VERSION = "1.0"
STUDIO_NINJA_AUTOMATION_AFTER = date(2026, 10, 20)
MINIMUM_PRE_CEREMONY_MINUTES = 60
CEREMONY_ARRIVAL_BUFFER_MINUTES = 15
COVERAGE_WARNING_GRACE_MINUTES = 15
MAX_AUTOMATIC_EARLIER_START_MINUTES = 60


class FinalTimingsAnswers(BaseModel):
    ceremony_time: time
    ceremony_duration: int = Field(default=45, ge=10, le=180)
    ceremony_venue: str = Field(min_length=2, max_length=1000)
    reception_same: bool = False
    reception_venue: str | None = Field(default=None, max_length=1000)

    prep_photos: bool = True
    prep_person: str | None = Field(default=None, max_length=300)
    prep_venue: str | None = Field(default=None, max_length=1000)
    travel_minutes: int = Field(default=0, ge=0, le=180)
    start_choice: Literal["normal", "earlier"] = "normal"
    requested_start: time | None = None
    prep_notes: str | None = Field(default=None, max_length=5000)
    second_prep: str | None = Field(default=None, max_length=2000)

    group_photo_time: time | None = None
    meal_time: time | None = None
    speeches_time: time | None = None
    speeches_position: Literal["Before the meal", "Between courses", "After the meal"] = "After the meal"
    evening_time: time | None = None
    cake_time: time | None = None
    first_dance_time: time
    later_event: bool = False
    later_event_name: str | None = Field(default=None, max_length=300)
    later_event_time: time | None = None
    extra_stops: str | None = Field(default=None, max_length=5000)

    day_contact: str = Field(min_length=2, max_length=300)
    day_mobile: str = Field(min_length=5, max_length=80)
    coordinator: str | None = Field(default=None, max_length=300)
    group_count: Literal["None", "1-5", "6-10", "More than 10"] = "1-5"
    important_notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="before")
    @classmethod
    def normalise_browser_values(cls, raw):
        values = dict(raw or {})
        optional = {
            "reception_venue", "prep_person", "prep_venue", "requested_start",
            "prep_notes", "second_prep", "group_photo_time", "meal_time",
            "speeches_time", "evening_time", "cake_time", "later_event_name",
            "later_event_time", "extra_stops", "coordinator", "important_notes",
        }
        for key in optional:
            if values.get(key) == "":
                values[key] = None
        return values

    @model_validator(mode="after")
    def conditional_answers_are_complete(self):
        if not self.reception_same and not self.reception_venue:
            raise ValueError("Please give the reception venue and full address.")
        if self.prep_photos and (not self.prep_person or not self.prep_venue):
            raise ValueError("Please complete who is getting ready and the preparation venue.")
        if self.start_choice == "earlier" and not self.requested_start:
            raise ValueError("Please choose the earlier photography start you would like to request.")
        if self.later_event and (not self.later_event_name or not self.later_event_time):
            raise ValueError("Please describe the essential event after the first dance and give its time.")
        return self


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _clock(value: int) -> str:
    normalised = value % (24 * 60)
    return f"{normalised // 60:02d}:{normalised % 60:02d}"


def _after(value: int, reference: int) -> int:
    return value + (24 * 60 if value < reference else 0)


def _normalised_package_text(booking: Booking, quote: Quote | None) -> str:
    parts = []
    if quote:
        for item in quote.line_items or []:
            if str(item.get("type") or "").lower() == "package":
                parts.extend([str(item.get("code") or ""), str(item.get("name") or "")])
    if not any(part.strip() for part in parts):
        parts.append(booking.package_name or "")
    return " ".join(parts).lower()


def booking_coverage_allowance(db: Session, booking: Booking) -> dict:
    quote = db.scalar(select(Quote).where(
        Quote.booking_id == booking.id,
        Quote.status == "accepted",
    ).order_by(Quote.accepted_at.desc(), Quote.created_at.desc()).limit(1))
    package_text = _normalised_package_text(booking, quote)
    if any(marker in package_text for marker in ("bronze", "package 1", "half day")):
        base_minutes = 240
    elif any(marker in package_text for marker in (
        "silver", "gold", "platinum", "ultimate", "package 2", "package 3",
        "package 4", "full day",
    )):
        base_minutes = 480
    else:
        base_minutes = None

    extra_hours = 0
    if quote:
        for item in quote.line_items or []:
            if str(item.get("type") or "").lower() != "addon":
                continue
            marker = f"{item.get('code') or ''} {item.get('name') or ''}".lower()
            if "extra_hour" in marker or re.search(r"\bextra\s+hour\b", marker):
                try:
                    extra_hours += max(1, int(item.get("quantity") or 1))
                except (TypeError, ValueError):
                    extra_hours += 1
    allowance = base_minutes + extra_hours * 60 if base_minutes is not None else None
    return {
        "base_minutes": base_minutes,
        "extra_hours": extra_hours,
        "allowance_minutes": allowance,
        "grace_minutes": COVERAGE_WARNING_GRACE_MINUTES,
        "package_name": booking.package_name,
    }


def final_timings_unlocked(db: Session, booking: Booking, today: date | None = None) -> bool:
    if booking.kind != RecordKind.WEDDING:
        return False
    if booking.status not in (
        RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS, RecordStatus.COMPLETED,
    ):
        return False
    if db.scalar(select(FormSubmission.id).where(
        FormSubmission.booking_id == booking.id,
        FormSubmission.form_type == FORM_TYPE,
    ).limit(1)):
        return True
    if (booking.workflow_state or {}).get("final_details_manual_unlock") is True:
        return True
    if not booking.event_date:
        return False
    return (booking.event_date - (today or date.today())).days <= 30


def studio_ninja_final_timings_email_due(
    booking: Booking, today: date | None = None,
) -> bool:
    current = today or date.today()
    return bool(
        booking.legacy_source == "studio_ninja"
        and booking.brand == Brand.WBM
        and booking.kind == RecordKind.WEDDING
        and booking.status in (RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS)
        and booking.event_date
        and booking.event_date > STUDIO_NINJA_AUTOMATION_AFTER
        and (booking.event_date - current).days == 30
    )


def calculate_final_timings(answers: FinalTimingsAnswers, allowance: dict) -> dict:
    ceremony = _minutes(answers.ceremony_time)
    normal_start = ceremony - MINIMUM_PRE_CEREMONY_MINUTES
    first_dance = _after(_minutes(answers.first_dance_time), normal_start)
    finish = first_dance
    if answers.later_event and answers.later_event_time:
        finish = max(finish, _after(_minutes(answers.later_event_time), normal_start))

    included = allowance.get("allowance_minutes")
    base_coverage = max(0, finish - normal_start)
    spare = max(0, included - base_coverage) if included is not None else 0
    use_requested = answers.start_choice == "earlier" and answers.requested_start is not None
    earlier_from_spare = (
        min(spare, MAX_AUTOMATIC_EARLIER_START_MINUTES)
        if not use_requested and answers.prep_photos and answers.travel_minutes > 0
        else 0
    )
    requested = _minutes(answers.requested_start) if answers.requested_start else normal_start
    start = min(requested, normal_start) if use_requested else normal_start - earlier_from_spare
    coverage = max(0, finish - start)

    over_standard = max(0, coverage - included) if included is not None else None
    flagged = bool(included is not None and coverage > included + COVERAGE_WARNING_GRACE_MINUTES)
    within_grace = bool(included is not None and included < coverage <= included + COVERAGE_WARNING_GRACE_MINUTES)
    extra_hours = math.ceil(over_standard / 60) if flagged and over_standard else 0

    target_ceremony_arrival = ceremony - CEREMONY_ARRIVAL_BUFFER_MINUTES
    prep_departure = target_ceremony_arrival - answers.travel_minutes
    prep_window = max(0, prep_departure - start) if answers.prep_photos else 0
    travel_warning = bool(answers.prep_photos and answers.travel_minutes > 0 and prep_window < 30)

    if included is None:
        status = "package_review"
    elif flagged:
        status = "over"
    elif within_grace:
        status = "within_grace"
    else:
        status = "within"

    timeline = []
    if answers.prep_photos:
        timeline.append({
            "time": _clock(start),
            "event": "Arrive for preparation photographs",
            "detail": f"{answers.prep_person} - {answers.prep_venue}",
        })
        if answers.travel_minutes:
            timeline.append({
                "time": _clock(prep_departure),
                "event": "Leave for ceremony",
                "detail": (
                    f"Allow approximately {answers.travel_minutes} minutes travelling and "
                    f"arrive {CEREMONY_ARRIVAL_BUFFER_MINUTES} minutes before the ceremony"
                ),
            })
    else:
        timeline.append({
            "time": _clock(start),
            "event": "Arrive at ceremony venue",
            "detail": answers.ceremony_venue,
        })

    timed_events = [
        (ceremony, "Ceremony", answers.ceremony_venue),
        (ceremony + answers.ceremony_duration, "Ceremony finishes (approximately)", answers.ceremony_venue),
        (answers.group_photo_time, "Group photographs", answers.group_count),
        (answers.meal_time, "Wedding breakfast / meal", answers.reception_venue or answers.ceremony_venue),
        (answers.speeches_time, "Speeches", answers.speeches_position),
        (answers.evening_time, "Evening guests arrive", answers.reception_venue or answers.ceremony_venue),
        (answers.cake_time, "Cake cutting", answers.reception_venue or answers.ceremony_venue),
        (answers.first_dance_time, "First dance", "Expected coverage finish"),
    ]
    for value, event, detail in timed_events:
        if value is None:
            continue
        event_minutes = value if isinstance(value, int) else _after(_minutes(value), start)
        timeline.append({"time": _clock(event_minutes), "event": event, "detail": str(detail or "")})
    if answers.later_event and answers.later_event_time:
        timeline.append({
            "time": _clock(_after(_minutes(answers.later_event_time), start)),
            "event": answers.later_event_name or "Essential later photograph",
            "detail": "Requested after the first dance",
        })

    def timeline_sort_key(item: dict) -> int:
        value = time.fromisoformat(item["time"])
        return _after(_minutes(value), start)

    timeline.sort(key=timeline_sort_key)
    return {
        "form_version": FORM_VERSION,
        "status": status,
        "package_name": allowance.get("package_name"),
        "package_allowance_minutes": included,
        "base_package_minutes": allowance.get("base_minutes"),
        "included_extra_hours": allowance.get("extra_hours", 0),
        "grace_minutes": COVERAGE_WARNING_GRACE_MINUTES,
        "minimum_pre_ceremony_minutes": MINIMUM_PRE_CEREMONY_MINUTES,
        "suggested_start": _clock(start),
        "normal_start": _clock(normal_start),
        "expected_finish": _clock(finish),
        "coverage_minutes": coverage,
        "over_standard_minutes": over_standard,
        "additional_hours_suggested": extra_hours,
        "earlier_start_minutes": earlier_from_spare,
        "ceremony_arrival_target": _clock(target_ceremony_arrival),
        "prep_departure": _clock(prep_departure) if answers.prep_photos else None,
        "prep_window_minutes": prep_window if answers.prep_photos else None,
        "coverage_warning": flagged,
        "travel_warning": travel_warning,
        "timeline": timeline,
    }


def validated_final_timings(db: Session, booking: Booking, raw: dict) -> dict:
    answers = FinalTimingsAnswers.model_validate(raw)
    clean = answers.model_dump(mode="json")
    for key, value in list(clean.items()):
        if isinstance(value, str):
            clean[key] = value.strip()
    for key in (
        "ceremony_time", "requested_start", "group_photo_time", "meal_time",
        "speeches_time", "evening_time", "cake_time", "first_dance_time",
        "later_event_time",
    ):
        if clean.get(key):
            clean[key] = clean[key][:5]
    clean["_calculation"] = calculate_final_timings(
        answers, booking_coverage_allowance(db, booking)
    )
    return clean

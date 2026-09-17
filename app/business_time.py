"""UK business-date and automatic-delivery window helpers.

Database timestamps remain UTC. Dates that drive Mark's client workflow are
calculated in Europe/London so midnight and British Summer Time cannot move a
reminder onto the wrong day.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


BUSINESS_TIMEZONE_NAME = "Europe/London"
BUSINESS_TIMEZONE = ZoneInfo(BUSINESS_TIMEZONE_NAME)


def business_now(now: datetime | None = None) -> datetime:
    """Return an aware Europe/London datetime."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(BUSINESS_TIMEZONE)


def business_today(now: datetime | None = None) -> date:
    return business_now(now).date()


def business_date(value: datetime) -> date:
    """Convert a stored UTC timestamp to the corresponding UK business date."""
    return business_now(value).date()


def automatic_delivery_allowed(
    start_hour: int,
    end_hour: int,
    *,
    now: datetime | None = None,
) -> bool:
    """True only inside the configured half-open UK delivery window."""
    local_now = business_now(now)
    opening = datetime.combine(local_now.date(), time(start_hour), BUSINESS_TIMEZONE)
    if end_hour == 24:
        closing = datetime.combine(
            local_now.date() + timedelta(days=1), time(0), BUSINESS_TIMEZONE
        )
    else:
        closing = datetime.combine(local_now.date(), time(end_hour), BUSINESS_TIMEZONE)
    return opening <= local_now < closing


def automatic_delivery_window_label(start_hour: int, end_hour: int) -> str:
    return f"{start_hour:02d}:00-{end_hour:02d}:00 {BUSINESS_TIMEZONE_NAME}"

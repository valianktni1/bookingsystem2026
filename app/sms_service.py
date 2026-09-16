"""The SMS Works integration used by the V8.49 SMS centre.

Sending is opt-in twice: the provider must be configured in the environment,
and each automatic template must be active.  No credential is stored in the
database or returned to the browser.
"""

from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Booking, BusinessProfile, SmsMessage, SmsTemplate, Task
from .services import audit, payment_reference


settings = get_settings()

SMS_AUTOMATION_LABELS: dict[str, str] = {
    "quote_followup_1": "Quote check - next day",
    "quote_followup_final": "Quote final check - nine days",
    "deposit_due_1": "Booking fee due",
    "check_in_120": "120-day wedding check-in",
    "check_in_30": "30-day final timings check-in",
    "balance_due_7": "Balance reminder - seven days",
    "balance_due_1": "Balance reminder - day before",
}

# GSM 03.38 basic and extension tables. Extension characters consume two
# septets; any other character makes the complete message Unicode.
GSM_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ"
    " !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
    "abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM_EXTENSION = set("^{}\\[~]|€")


class SmsDeliveryError(RuntimeError):
    pass


def sms_ready() -> bool:
    if not settings.sms_enabled or not settings.sms_api_token:
        return False
    try:
        sms_sender()
    except ValueError:
        return False
    return True


def normalise_sms_number(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("This client does not have a mobile number saved")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0044"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = "44" + digits[1:]
    if not re.fullmatch(r"447\d{9}", digits):
        raise ValueError("Use a valid UK mobile number, for example 07712 345678")
    return digits


def sms_sender() -> str:
    if settings.sms_reply_number:
        return normalise_sms_number(settings.sms_reply_number)
    sender = settings.sms_sender_id.strip()
    if not (4 <= len(sender) <= 11 and sender.isalnum()):
        raise ValueError("SMS sender name must be 4 to 11 letters/numbers with no spaces")
    return sender


def sms_parts(body: str) -> dict[str, int | bool | str]:
    gsm = all(char in GSM_BASIC or char in GSM_EXTENSION for char in body)
    if gsm:
        units = sum(2 if char in GSM_EXTENSION else 1 for char in body)
        parts = 1 if units <= 160 else math.ceil(units / 153)
        return {"characters": len(body), "units": units, "parts": parts, "unicode": False,
                "encoding": "GSM"}
    units = len(body)
    parts = 1 if units <= 70 else math.ceil(units / 67)
    return {"characters": len(body), "units": units, "parts": parts, "unicode": True,
            "encoding": "Unicode"}


def provider_send_sms(*, destination: str, sender: str, content: str,
                      metadata: list[dict[str, str]]) -> dict[str, Any]:
    if not sms_ready():
        raise SmsDeliveryError("SMS is not enabled or the API token is missing")
    payload = json.dumps({
        "sender": sender,
        "destination": destination,
        "content": content,
        "metadata": metadata,
        # Keep Mark's exact reviewed wording. Provider-side AI rewriting is off.
        "ai": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{settings.sms_api_url.rstrip('/')}/message/send",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": str(settings.sms_api_token),
            "User-Agent": "BookingSystem2026/8.49",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.sms_timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
            message = detail.get("message") or detail.get("error") or detail.get("errorMessage")
        except (json.JSONDecodeError, AttributeError):
            message = None
        raise SmsDeliveryError(
            f"The SMS Works rejected the text ({exc.code})"
            + (f": {str(message)[:300]}" if message else "")
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SmsDeliveryError("The SMS Works could not be reached; no delivery was confirmed") from exc
    if status != 201:
        raise SmsDeliveryError(f"The SMS Works returned an unexpected response ({status})")
    try:
        result = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise SmsDeliveryError("The SMS Works accepted the request but returned an unreadable receipt") from exc
    if isinstance(result, str):
        result = {"messageid": result}
    if not isinstance(result, dict):
        raise SmsDeliveryError("The SMS Works returned an unexpected receipt")
    message_id = result.get("messageid") or result.get("messageId") or result.get("id")
    if not message_id:
        raise SmsDeliveryError("The SMS Works did not return a message reference")
    result["messageid"] = str(message_id)
    return result


def sms_template_values(booking: Booking, profile: BusinessProfile) -> dict[str, str]:
    event_date = booking.event_date.strftime("%A %d %B %Y") if booking.event_date else "your wedding date"
    balance_date = booking.balance_due_date.strftime("%d %B %Y") if booking.balance_due_date else "the agreed date"
    total = Decimal(str(booking.quoted_total or 0))
    client_name = " ".join(filter(None, [booking.client.first_name, booking.client.last_name])).strip()
    return {
        "client_first_name": booking.client.first_name or "there",
        "client_name": client_name or booking.title,
        "partner_name": booking.client.partner_name or "",
        "business_name": profile.display_name,
        "business_phone": profile.phone or "",
        "event_date": event_date,
        "venue": booking.venue_or_project or "your venue",
        "balance_due_date": balance_date,
        "payment_reference": payment_reference(booking),
        "quoted_total": f"£{total:,.2f}",
    }


def render_sms_template(template: SmsTemplate, booking: Booking,
                        profile: BusinessProfile) -> str:
    body = template.body
    for key, value in sms_template_values(booking, profile).items():
        body = body.replace("{" + key + "}", value)
    return body.strip()


def booking_sms_destination(db: Session, booking: Booking) -> tuple[str, bool]:
    destination = normalise_sms_number(booking.client.phone)
    if booking.is_test:
        if not settings.sms_test_number:
            raise ValueError("Set SMS_TEST_NUMBER before sending a text from a TEST booking")
        return normalise_sms_number(settings.sms_test_number), True
    return destination, False


def send_booking_sms(
    db: Session,
    booking: Booking,
    body: str,
    *,
    template_key: str | None = None,
    automated: bool = False,
    dedupe_key: str | None = None,
    send_callable: Callable[..., dict[str, Any]] | None = None,
) -> tuple[SmsMessage, bool]:
    """Persist then send one SMS. Returns ``(message, sent_successfully)``."""
    content = body.strip()
    if not content:
        raise ValueError("Write a message before sending")
    if len(content) > 1280:
        raise ValueError("SMS messages cannot be longer than 1,280 characters")
    destination, redirected = booking_sms_destination(db, booking)
    sender = sms_sender()
    estimate = sms_parts(content)
    row = SmsMessage(
        booking_id=booking.id,
        brand=booking.brand,
        direction="outgoing",
        template_key=template_key,
        recipient=destination,
        sender=sender,
        body=content,
        status="sending",
        parts=int(estimate["parts"]),
        automated=automated,
        dedupe_key=dedupe_key,
        provider_data={"test_redirected": redirected, "estimated": estimate},
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if dedupe_key:
            existing = db.scalar(select(SmsMessage).where(SmsMessage.dedupe_key == dedupe_key))
            if existing:
                return existing, existing.status in {"sent", "delivered"}
        raise
    try:
        result = (send_callable or provider_send_sms)(
            destination=destination,
            sender=sender,
            content=content,
            metadata=[
                {"key": "booking_id", "value": booking.id},
                {"key": "sms_message_id", "value": row.id},
            ],
        )
        row.provider_message_id = str(result["messageid"])
        row.status = "sent"
        row.sent_at = datetime.now(timezone.utc)
        row.error = None
        row.provider_data = {**(row.provider_data or {}), "receipt": {
            key: value for key, value in result.items()
            if key.lower() not in {"token", "authorization", "apikey", "secret"}
        }}
        for task in db.scalars(select(Task).where(
            Task.booking_id == booking.id,
            Task.workflow_key.like("sms_reply:%"),
            Task.completed.is_(False),
        )).all():
            task.completed = True
        audit(db, "send_automatic_sms" if automated else "send_sms", "booking", booking.id, {
            "template": template_key,
            "provider_message_id": row.provider_message_id,
            "parts": row.parts,
            "test_redirected": redirected,
        })
        db.commit()
        return row, True
    except Exception as exc:
        row.status = "failed"
        row.error = str(exc)[:2000]
        if automated:
            db.add(Task(
                booking_id=booking.id,
                title="Review a failed automatic text message",
                workflow_key=f"sms_send:{row.id}",
                due_at=datetime.now(timezone.utc),
            ))
        audit(db, "automatic_sms_failed" if automated else "sms_failed", "booking", booking.id, {
            "template": template_key,
            "error": row.error,
            "test_redirected": redirected,
        })
        db.commit()
        return row, False


def sms_message_json(row: SmsMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "booking_id": row.booking_id,
        "brand": row.brand.value,
        "direction": row.direction,
        "template_key": row.template_key,
        "recipient": row.recipient,
        "sender": row.sender,
        "body": row.body,
        "status": row.status,
        "provider_message_id": row.provider_message_id,
        "parts": row.parts,
        "automated": row.automated,
        "error": row.error,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
        "received_at": row.received_at.isoformat() if row.received_at else None,
        "created_at": row.created_at.isoformat(),
    }

"""Private progress emails sent to Mark, never to the couple (V8.36)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .email_service import render_template_content, send_rendered_email, smtp_ready
from .models import AuditLog, Booking, Brand, BusinessProfile, EmailLog, EmailTemplate


OWNER_NOTIFICATION_KEYS = frozenset({
    "new_enquiry_admin",
    "quote_accepted_admin",
    "booking_form_submitted_admin",
    "final_timings_submitted_admin",
    "contract_signed_admin",
})

settings = get_settings()


def owner_notification_recipient(booking: Booking) -> str:
    """Testing Mode keeps even private alerts inside the selected test mailbox."""
    if booking.is_test:
        testing_email = str((booking.workflow_state or {}).get("test_email") or "").strip()
        if testing_email:
            return testing_email.lower()
    return settings.admin_email.lower()


def send_owner_notification_safely(
    db: Session,
    booking: Booking,
    template_key: str,
    *,
    section: str = "overview",
    extra_values: dict[str, str] | None = None,
) -> dict:
    """Send one owner alert after the client action is durable.

    Delivery failure is retained for the existing communication-retry queue and
    is never allowed to roll back a quote, form or signed agreement.
    """
    if template_key not in OWNER_NOTIFICATION_KEYS - {"new_enquiry_admin"}:
        raise ValueError("Unknown private owner-notification template")
    recipient = owner_notification_recipient(booking)
    attempted_at = datetime.now(timezone.utc)
    template = db.scalar(select(EmailTemplate).where(
        EmailTemplate.brand == Brand.WBM,
        EmailTemplate.template_key == template_key,
        EmailTemplate.is_active.is_(True),
    ))
    profile = db.scalar(select(BusinessProfile).where(BusinessProfile.brand == Brand.WBM))
    values = {
        "admin_url": (
            f"{settings.app_url.rstrip('/')}/bookings/{booking.id}/{section}"
        ),
        **(extra_values or {}),
    }

    unavailable = None
    if booking.brand != Brand.WBM:
        unavailable = "Private progress alerts apply only to Weddings By Mark bookings"
    elif not template:
        unavailable = f"The private notification template {template_key} is missing or inactive"
    elif not profile:
        unavailable = "The Weddings By Mark business profile is missing"
    elif not smtp_ready(Brand.WBM):
        unavailable = "Weddings By Mark SMTP is not configured"
    if unavailable:
        db.add(AuditLog(
            action="owner_notification_not_sent",
            entity_type="booking",
            entity_id=booking.id,
            details={
                "template": template_key,
                "recipient": recipient,
                "reason": unavailable,
                "client_action_preserved": True,
            },
        ))
        db.commit()
        return {"sent": False, "status": "unavailable", "error": unavailable}

    subject, body = render_template_content(
        booking, profile, template, extra_values=values,
    )
    try:
        send_rendered_email(
            booking,
            profile,
            recipient,
            subject,
            body,
            reply_to=booking.client.email,
        )
        db.add(EmailLog(
            booking_id=booking.id,
            template_key=template_key,
            recipient=recipient,
            subject=subject,
            body=body,
            status="sent",
            last_attempt_at=attempted_at,
            sent_at=attempted_at,
        ))
        db.add(AuditLog(
            action="owner_notification_sent",
            entity_type="booking",
            entity_id=booking.id,
            details={
                "template": template_key,
                "recipient": recipient,
                "client_action_preserved": True,
            },
        ))
        db.commit()
        return {"sent": True, "status": "sent", "recipient": recipient}
    except Exception as exc:
        error = str(exc)[:2000] or "Private notification delivery failed"
        db.add(EmailLog(
            booking_id=booking.id,
            template_key=template_key,
            recipient=recipient,
            subject=subject,
            body=body,
            status="failed",
            error=error,
            last_attempt_at=attempted_at,
            next_attempt_at=attempted_at,
        ))
        db.add(AuditLog(
            action="owner_notification_failed",
            entity_type="booking",
            entity_id=booking.id,
            details={
                "template": template_key,
                "recipient": recipient,
                "error": error,
                "client_action_preserved": True,
            },
        ))
        db.commit()
        return {"sent": False, "status": "failed", "error": error}

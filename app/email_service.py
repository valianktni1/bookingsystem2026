import smtplib
import ssl
from email.message import EmailMessage

from .config import get_settings
from .models import Booking, Brand, BusinessProfile, EmailTemplate


def template_values(booking: Booking, profile: BusinessProfile, portal_url: str | None = None) -> dict[str, str]:
    client = booking.client
    return {
        "client_first_name": client.first_name or "there",
        "client_name": " ".join(x for x in [client.first_name, client.last_name] if x),
        "couple_or_company": booking.title,
        "business_name": profile.display_name,
        "event_date": booking.event_date.strftime("%d %B %Y") if booking.event_date else "to be confirmed",
        "venue_or_project": booking.venue_or_project or "to be confirmed",
        "package_name": booking.package_name or "your chosen service",
        "quoted_total": f"£{float(booking.quoted_total or 0):,.2f}",
        "deposit_amount": f"£{float(booking.deposit_amount or 0):,.2f}",
        "balance_due_date": booking.balance_due_date.strftime("%d %B %Y") if booking.balance_due_date else "as shown on your invoice",
        "portal_url": portal_url or "",
        "business_email": profile.email or "",
        "business_phone": profile.phone or "",
    }


def render_template(text: str, values: dict[str, str]) -> str:
    rendered = text
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def smtp_credentials(brand: Brand | None = None) -> tuple[str | None, str | None]:
    settings = get_settings()
    if brand == Brand.WBM:
        return (settings.smtp_wbm_username or settings.smtp_username,
                settings.smtp_wbm_password or settings.smtp_password)
    if brand == Brand.IVORY:
        return (settings.smtp_ivory_username or settings.smtp_username,
                settings.smtp_ivory_password or settings.smtp_password)
    return settings.smtp_username, settings.smtp_password


def smtp_ready(brand: Brand | None = None) -> bool:
    settings = get_settings()
    if brand is None:
        return smtp_ready(Brand.WBM) or smtp_ready(Brand.IVORY)
    username, password = smtp_credentials(brand)
    return bool(settings.smtp_host and username and password)


def send_template_email(booking: Booking, profile: BusinessProfile, template: EmailTemplate,
                        portal_url: str | None = None) -> tuple[str, str]:
    settings = get_settings()
    username, password = smtp_credentials(booking.brand)
    if not smtp_ready(booking.brand):
        raise RuntimeError("SMTP is not configured. Add SMTP_USERNAME and SMTP_PASSWORD to the Dockge YAML.")
    values = template_values(booking, profile, portal_url)
    subject = render_template(template.subject, values)
    body = render_template(template.body, values)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{profile.display_name} <{username}>"
    message["To"] = booking.client.email
    message["Reply-To"] = profile.email or username
    message.set_content(body)
    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=30) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(username, password)
            server.send_message(message)
    return subject, body

import html
import re
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path

from .config import get_settings
from .models import Booking, Brand, BusinessProfile, EmailTemplate
from .services import payment_reference


BRANDING_DIR = Path(__file__).parent / "static" / "branding"
BRAND_ASSETS = {
    Brand.WBM: {
        "logo": BRANDING_DIR / "weddings-by-mark-logo.png",
        "logo_cid": "weddings-by-mark-logo",
        "awards": BRANDING_DIR / "weddings-by-mark-awards.png",
        "awards_cid": "weddings-by-mark-awards",
        "accent": "#b6924f",
        "soft": "#f8f5ef",
    },
    Brand.IVORY: {
        "logo": BRANDING_DIR / "ivory-digital-logo.png",
        "logo_cid": "ivory-digital-logo",
        "accent": "#bb8c36",
        "soft": "#fbf6eb",
    },
}


def template_values(booking: Booking, profile: BusinessProfile, portal_url: str | None = None,
                    extra_values: dict[str, str] | None = None) -> dict[str, str]:
    client = booking.client
    bank = profile.bank_details or {}
    final_call_date = None
    if booking.event_date:
        # The call is on the Monday immediately before the wedding. For a
        # Monday wedding, "before" means the previous Monday, never the day
        # of the wedding itself.
        days_back = booking.event_date.weekday() or 7
        final_call_date = booking.event_date - timedelta(days=days_back)
    values = {
        "client_first_name": client.first_name or "there",
        "client_name": " ".join(x for x in [client.first_name, client.last_name] if x),
        "client_email": client.email or "",
        "client_phone": client.phone or "Not provided",
        "couple_or_company": booking.title,
        "business_name": profile.display_name,
        "event_date": booking.event_date.strftime("%d %B %Y") if booking.event_date else "to be confirmed",
        "venue_or_project": booking.venue_or_project or "to be confirmed",
        "package_name": booking.package_name or "your chosen service",
        "quoted_total": f"£{float(booking.quoted_total or 0):,.2f}",
        "deposit_amount": f"£{float(booking.deposit_amount or 0):,.2f}",
        "deposit_due_date": "within one day of accepting your quote",
        "balance_due_date": booking.balance_due_date.strftime("%d %B %Y") if booking.balance_due_date else "as shown on your invoice",
        "final_call_date": (f"Monday {final_call_date.strftime('%d %B %Y')}"
                            if final_call_date else "the Monday before your wedding"),
        "portal_url": portal_url or "",
        "payment_amount": "£100.00",
        "payment_date": "today",
        "invoice_number": "WBM02001" if booking.brand == Brand.WBM else "ID02001",
        "payment_reference": payment_reference(
            booking, "shown on your invoice" if booking.brand == Brand.WBM else "ID02001"
        ),
        "total_paid": "£100.00",
        "deposit_remaining": "£0.00",
        "outstanding_balance": f"£{max(0, float(booking.quoted_total or 0) - 100):,.2f}",
        "payment_status": "Your booking is secured",
        "business_email": profile.email or "",
        "business_phone": profile.phone or "",
        "bank_account_name": bank.get("account_name") or "as shown on your invoice",
        "bank_sort_code": bank.get("sort_code") or "as shown on your invoice",
        "bank_account_number": bank.get("account_number") or "as shown on your invoice",
    }
    values.update(extra_values or {})
    return values


def render_template(text: str, values: dict[str, str]) -> str:
    rendered = text
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def ensure_client_account_link(body: str, booking: Booking,
                               portal_url: str | None) -> str:
    """Guarantee the correct secure-account link in every client email."""
    if not portal_url or portal_url in body:
        return body
    label = ("View your wedding account, invoices and booking details"
             if booking.brand == Brand.WBM
             else "View your client account, invoices and project details")
    return f"{body.rstrip()}\n\n[{label.upper()}]({portal_url})"


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


def send_email_message(message: EmailMessage, brand: Brand) -> None:
    """Send an already-built message through the selected business mailbox."""
    settings = get_settings()
    username, password = smtp_credentials(brand)
    if not smtp_ready(brand):
        raise RuntimeError("SMTP is not configured for this business mailbox")
    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context,
                              timeout=settings.mail_timeout_seconds) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port,
                          timeout=settings.mail_timeout_seconds) as server:
            server.starttls(context=context)
            server.login(username, password)
            server.send_message(message)


def _body_html(body: str) -> str:
    """Safely turn the editable plain-text template into email-friendly HTML."""
    buttons: list[str] = []

    def button(match: re.Match) -> str:
        label = html.escape(match.group(1).strip())
        url = html.escape(match.group(2), quote=True)
        buttons.append(
            f'<a href="{url}" style="display:inline-block;padding:14px 22px;'
            'border-radius:8px;background:#76591f;color:#ffffff;text-decoration:none;'
            f'font-weight:bold;letter-spacing:.4px;text-align:center">{label}</a>'
        )
        return f"@@PORTAL_BUTTON_{len(buttons) - 1}@@"

    # Template writers can use [BUTTON WORDING]({portal_url}). This keeps the
    # editable template readable while the HTML email gets a polished button.
    prepared = re.sub(r"\[([^\]\n]{1,100})\]\((https?://[^\s)]+)\)", button, body)
    rendered = html.escape(prepared)

    # Allow editable templates to highlight a short, trusted value with
    # **bold wording** while every character remains HTML-escaped first.
    rendered = re.sub(
        r"\*\*([^*\n]{1,160})\*\*",
        r'<strong style="font-weight:800;color:#5f461a">\1</strong>',
        rendered,
    )

    def link(match: re.Match) -> str:
        url = match.group(1)
        if "/client/" in url:
            label = ("VIEW YOUR PAYMENT RECEIPT"
                     if "open=receipt" in url else "OPEN YOUR SECURE ACCOUNT")
            return (
                f'<a href="{url}" style="display:inline-block;padding:14px 22px;'
                'border-radius:8px;background:#76591f;color:#ffffff;text-decoration:none;'
                'font-weight:bold;letter-spacing:.4px;text-align:center">'
                f'{label}</a>'
            )
        return (f'<a href="{url}" style="color:#76591f;text-decoration:underline;'
                f'word-break:break-all">{url}</a>')

    rendered = re.sub(r"(https?://[^\s<]+)", link, rendered)
    for index, markup in enumerate(buttons):
        rendered = rendered.replace(f"@@PORTAL_BUTTON_{index}@@", markup)
    return rendered.replace("\n", "<br>")


def _plain_body(body: str) -> str:
    """Keep accessible URLs in the plain-text alternative to the HTML email."""
    plain = re.sub(r"\[([^\]\n]{1,100})\]\((https?://[^\s)]+)\)",
                   lambda match: f"{match.group(1)}: {match.group(2)}", body)
    return re.sub(r"\*\*([^*\n]{1,160})\*\*", r"\1", plain)


def _email_html(body: str, booking: Booking, profile: BusinessProfile) -> str:
    assets = BRAND_ASSETS[booking.brand]
    awards = ""
    if booking.brand == Brand.WBM:
        awards = f"""
          <tr>
            <td style="padding:22px 28px 26px;border-top:1px solid #ece6da;text-align:center;background:#ffffff">
              <div style="font-family:Arial,sans-serif;font-size:11px;line-height:16px;letter-spacing:1.4px;color:#7c6a49;font-weight:bold;margin-bottom:12px">
                PROUDLY AWARD-WINNING WEDDING PHOTOGRAPHY
              </div>
              <img src="cid:{assets['awards_cid']}" width="340" alt="Weddings By Mark awards"
                   style="display:block;width:100%;max-width:340px;height:auto;margin:0 auto;border:0">
            </td>
          </tr>"""
    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f3f1ed;color:#262626">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f3f1ed">
      <tr>
        <td align="center" style="padding:24px 10px">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                 style="width:100%;max-width:640px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e7e2d8">
            <tr>
              <td align="center" style="padding:24px 28px;background:{assets['soft']};border-bottom:3px solid {assets['accent']}">
                <img src="cid:{assets['logo_cid']}" alt="{html.escape(profile.display_name)}"
                     style="display:block;max-width:{'280px' if booking.brand == Brand.IVORY else '245px'};max-height:{'94px' if booking.brand == Brand.IVORY else '150px'};width:auto;height:auto;margin:0 auto;border:0">
              </td>
            </tr>
            <tr>
              <td style="padding:32px 32px 28px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:25px;color:#2d2b28">
                {_body_html(body)}
              </td>
            </tr>
            <tr>
              <td style="padding:18px 28px;background:#242321;color:#ffffff;text-align:center;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:19px">
                <strong>{html.escape(profile.display_name)}</strong><br>
                {html.escape(profile.email or '')}{' &nbsp;·&nbsp; ' if profile.email and profile.phone else ''}{html.escape(profile.phone or '')}<br>
                {html.escape(profile.website or '')}
              </td>
            </tr>
            {awards}
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def build_email_message(booking: Booking, profile: BusinessProfile, subject: str, body: str,
                        username: str, recipient: str | None = None,
                        reply_to: str | None = None) -> EmailMessage:
    """Create a branded multipart email with embedded, client-safe PNG artwork."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{profile.display_name} <{username}>"
    message["To"] = recipient or booking.client.email
    message["Reply-To"] = reply_to or profile.email or username
    message.set_content(_plain_body(body))
    message.add_alternative(_email_html(body, booking, profile), subtype="html")
    html_part = message.get_payload()[-1]
    assets = BRAND_ASSETS[booking.brand]
    for path_key, cid_key in (("logo", "logo_cid"), ("awards", "awards_cid")):
        path = assets.get(path_key)
        if path and path.exists():
            html_part.add_related(path.read_bytes(), maintype="image", subtype="png",
                                  cid=f"<{assets[cid_key]}>", filename=path.name,
                                  disposition="inline")
    return message


def send_template_email(booking: Booking, profile: BusinessProfile, template: EmailTemplate,
                        portal_url: str | None = None,
                        extra_values: dict[str, str] | None = None,
                        recipient: str | None = None,
                        reply_to: str | None = None) -> tuple[str, str]:
    username, _ = smtp_credentials(booking.brand)
    if not smtp_ready(booking.brand):
        raise RuntimeError(
            f"SMTP is not configured for {profile.display_name}. "
            "Add that brand's SMTP username and mailbox password to the Dockge YAML."
        )
    subject, body = render_template_content(
        booking, profile, template, portal_url, extra_values
    )
    message = build_email_message(booking, profile, subject, body, username,
                                  recipient=recipient, reply_to=reply_to)
    try:
        send_email_message(message, booking.brand)
    except Exception as exc:
        # Callers can durably retain the exact attempted wording, allowing a
        # deliberate retry without silently changing to a newer template.
        exc.rendered_subject = subject
        exc.rendered_body = body
        raise
    return subject, body


def render_template_content(booking: Booking, profile: BusinessProfile,
                            template: EmailTemplate, portal_url: str | None = None,
                            extra_values: dict[str, str] | None = None) -> tuple[str, str]:
    """Render editable template wording without contacting the mail server."""
    values = template_values(booking, profile, portal_url, extra_values)
    subject = render_template(template.subject, values)
    body = ensure_client_account_link(
        render_template(template.body, values), booking, portal_url
    )
    return subject, body


def send_rendered_email(booking: Booking, profile: BusinessProfile, recipient: str,
                        subject: str, body: str) -> None:
    """Send a previously rendered, audit-retained message exactly as written."""
    username, _ = smtp_credentials(booking.brand)
    if not smtp_ready(booking.brand):
        raise RuntimeError(f"SMTP is not configured for {profile.display_name}")
    message = build_email_message(
        booking, profile, subject, body, username, recipient=recipient
    )
    send_email_message(message, booking.brand)


def preview_template_email(booking: Booking, profile: BusinessProfile, template: EmailTemplate,
                           portal_url: str | None = None) -> tuple[str, str, str]:
    """Render the exact subject, text and branded HTML without sending anything."""
    values = template_values(booking, profile, portal_url)
    subject = render_template(template.subject, values)
    body = ensure_client_account_link(
        render_template(template.body, values), booking, portal_url
    )
    return subject, _plain_body(body), _email_html(body, booking, profile)

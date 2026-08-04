import html
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from .config import get_settings
from .models import Booking, Brand, BusinessProfile, EmailTemplate


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
        "portal_url": portal_url or "",
        "business_email": profile.email or "",
        "business_phone": profile.phone or "",
    }
    values.update(extra_values or {})
    return values


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


def _body_html(body: str) -> str:
    """Safely turn the editable plain-text template into email-friendly HTML."""
    rendered = html.escape(body)
    rendered = re.sub(
        r"(https?://[^\s<]+)",
        r'<a href="\1" style="color:#76591f;text-decoration:underline;word-break:break-all">\1</a>',
        rendered,
    )
    return rendered.replace("\n", "<br>")


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
    message.set_content(body)
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
    settings = get_settings()
    username, password = smtp_credentials(booking.brand)
    if not smtp_ready(booking.brand):
        raise RuntimeError(
            f"SMTP is not configured for {profile.display_name}. "
            "Add that brand's SMTP username and mailbox password to the Dockge YAML."
        )
    values = template_values(booking, profile, portal_url, extra_values)
    subject = render_template(template.subject, values)
    body = render_template(template.body, values)
    message = build_email_message(booking, profile, subject, body, username,
                                  recipient=recipient, reply_to=reply_to)
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


def preview_template_email(booking: Booking, profile: BusinessProfile, template: EmailTemplate,
                           portal_url: str | None = None) -> tuple[str, str, str]:
    """Render the exact subject, text and branded HTML without sending anything."""
    values = template_values(booking, profile, portal_url)
    subject = render_template(template.subject, values)
    body = render_template(template.body, values)
    return subject, body, _email_html(body, booking, profile)

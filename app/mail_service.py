"""Secure Hostinger IMAP reading and threaded SMTP reply helpers."""

from __future__ import annotations

import html
import imaplib
import re
import ssl
import time
from contextlib import contextmanager, suppress
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import make_msgid, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator

from .config import get_settings
from .email_service import BRAND_ASSETS, _body_html, smtp_credentials
from .models import Brand, BusinessProfile


def imap_credentials(brand: Brand) -> tuple[str | None, str | None]:
    """Use explicit IMAP credentials, falling back to the same mailbox SMTP login."""
    settings = get_settings()
    if brand == Brand.WBM:
        return (
            settings.imap_wbm_username or settings.smtp_wbm_username or settings.smtp_username,
            settings.imap_wbm_password or settings.smtp_wbm_password or settings.smtp_password,
        )
    return (
        settings.imap_ivory_username or settings.smtp_ivory_username or settings.smtp_username,
        settings.imap_ivory_password or settings.smtp_ivory_password or settings.smtp_password,
    )


def imap_ready(brand: Brand | None = None) -> bool:
    settings = get_settings()
    if brand is None:
        return imap_ready(Brand.WBM) or imap_ready(Brand.IVORY)
    username, password = imap_credentials(brand)
    return bool(settings.imap_host and username and password)


@contextmanager
def imap_connection(brand: Brand, readonly: bool = True) -> Iterator[imaplib.IMAP4]:
    settings = get_settings()
    username, password = imap_credentials(brand)
    if not imap_ready(brand):
        raise RuntimeError("IMAP is not configured for this business mailbox")
    context = ssl.create_default_context()
    if settings.imap_use_ssl:
        connection = imaplib.IMAP4_SSL(
            settings.imap_host, settings.imap_port, ssl_context=context,
            timeout=settings.mail_timeout_seconds,
        )
    else:
        connection = imaplib.IMAP4(
            settings.imap_host, settings.imap_port,
            timeout=settings.mail_timeout_seconds,
        )
        connection.starttls(ssl_context=context)
    try:
        connection.login(username, password)
        status, _ = connection.select("INBOX", readonly=readonly)
        if status != "OK":
            raise RuntimeError("The mailbox inbox could not be opened")
        yield connection
    finally:
        with suppress(Exception):
            connection.close()
        with suppress(Exception):
            connection.logout()


def _decoded(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return str(value).strip()


def _date_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=__import__("datetime").timezone.utc)
        return parsed.isoformat()
    except Exception:
        return None


def _message_bytes(data) -> tuple[bytes, bytes] | None:
    for part in data or []:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
            return bytes(part[0]), part[1]
    return None


def _uid_from_meta(meta: bytes) -> str:
    match = re.search(rb"\bUID\s+(\d+)", meta)
    return match.group(1).decode("ascii") if match else ""


def _flags_from_meta(meta: bytes) -> list[str]:
    match = re.search(rb"FLAGS\s+\(([^)]*)\)", meta)
    if not match:
        return []
    return [item.decode("ascii", "ignore") for item in match.group(1).split()]


def mailbox_status(brand: Brand) -> dict:
    username, _ = imap_credentials(brand)
    result = {
        "brand": brand.value,
        "address": username,
        "configured": imap_ready(brand),
        "connected": False,
        "total": 0,
        "unread": 0,
        "error": None,
    }
    if not result["configured"]:
        return result
    try:
        with imap_connection(brand) as connection:
            status, all_data = connection.uid("search", None, "ALL")
            if status != "OK":
                raise RuntimeError("The mailbox could not be searched")
            status, unseen_data = connection.uid("search", None, "UNSEEN")
            if status != "OK":
                raise RuntimeError("Unread mail could not be checked")
            result["connected"] = True
            result["total"] = len((all_data[0] or b"").split())
            result["unread"] = len((unseen_data[0] or b"").split())
    except Exception as exc:
        result["error"] = friendly_mail_error(exc)
    return result


def list_inbox_messages(brand: Brand, limit: int | None = None, unread_only: bool = False) -> list[dict]:
    settings = get_settings()
    count = max(1, min(limit or settings.mail_list_limit, 200))
    with imap_connection(brand) as connection:
        status, data = connection.uid("search", None, "UNSEEN" if unread_only else "ALL")
        if status != "OK":
            raise RuntimeError("The inbox could not be searched")
        uids = (data[0] or b"").split()[-count:]
        if not uids:
            return []
        status, fetched = connection.uid(
            "fetch", b",".join(uids).decode("ascii"),
            "(BODY.PEEK[HEADER.FIELDS (FROM REPLY-TO TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES)] FLAGS)",
        )
        if status != "OK":
            raise RuntimeError("The inbox message list could not be loaded")
        rows: list[dict] = []
        for part in fetched or []:
            if not (isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes)):
                continue
            meta, raw_headers = bytes(part[0]), part[1]
            uid = _uid_from_meta(meta)
            if not uid:
                continue
            message = BytesParser(policy=policy.default).parsebytes(raw_headers)
            sender_name, sender_email = parseaddr(_decoded(message.get("From")))
            reply_name, reply_email = parseaddr(_decoded(message.get("Reply-To")))
            flags = _flags_from_meta(meta)
            rows.append({
                "uid": uid,
                "brand": brand.value,
                "from_name": _decoded(sender_name) or sender_email,
                "from_email": sender_email.lower(),
                "reply_to_email": (reply_email or sender_email).lower(),
                "to": _decoded(message.get("To")),
                "subject": _decoded(message.get("Subject")) or "(No subject)",
                "date": _date_iso(message.get("Date")),
                "message_id": _decoded(message.get("Message-ID")),
                "in_reply_to": _decoded(message.get("In-Reply-To")),
                "references": _decoded(message.get("References")),
                "unread": "\\Seen" not in flags,
                "flagged": "\\Flagged" in flags,
            })
        rows.sort(key=lambda item: (item.get("date") or "", int(item["uid"])), reverse=True)
        return rows


class _TextExtractor(HTMLParser):
    block_tags = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts).replace("\r", "")
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _part_text(part: Message) -> str:
    try:
        content = part.get_content()
        if isinstance(content, bytes):
            return content.decode(part.get_content_charset() or "utf-8", "replace")
        return str(content)
    except Exception:
        payload = part.get_payload(decode=True) or b""
        return payload.decode(part.get_content_charset() or "utf-8", "replace")


def message_text(message: EmailMessage) -> str:
    plain: list[str] = []
    rich: list[str] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain.append(_part_text(part))
        elif content_type == "text/html":
            parser = _TextExtractor()
            parser.feed(_part_text(part))
            rich.append(parser.text())
    text = "\n\n".join(item.strip() for item in (plain or rich) if item.strip())
    return text[:200_000] or "This email does not contain a readable text body."


def attachment_parts(message: EmailMessage) -> list[Message]:
    rows: list[Message] = []
    for part in message.walk():
        filename = part.get_filename()
        if part.is_multipart():
            continue
        if filename or part.get_content_disposition() == "attachment":
            rows.append(part)
    return rows


def _fetch_message(connection: imaplib.IMAP4, uid: str) -> tuple[bytes, EmailMessage]:
    if not re.fullmatch(r"\d{1,20}", str(uid)):
        raise ValueError("Invalid message reference")
    status, data = connection.uid("fetch", str(uid), "(BODY.PEEK[] FLAGS)")
    if status != "OK":
        raise RuntimeError("The email could not be opened")
    found = _message_bytes(data)
    if not found:
        raise FileNotFoundError("The email is no longer available in the inbox")
    meta, raw = found
    return meta, BytesParser(policy=policy.default).parsebytes(raw)


def read_inbox_message(brand: Brand, uid: str, mark_seen: bool = True) -> dict:
    with imap_connection(brand, readonly=not mark_seen) as connection:
        meta, message = _fetch_message(connection, uid)
        if mark_seen:
            connection.uid("store", str(uid), "+FLAGS", "(\\Seen)")
        sender_name, sender_email = parseaddr(_decoded(message.get("From")))
        reply_name, reply_email = parseaddr(_decoded(message.get("Reply-To")))
        attachments = attachment_parts(message)
        flags = _flags_from_meta(meta)
        return {
            "uid": str(uid),
            "brand": brand.value,
            "from_name": _decoded(sender_name) or sender_email,
            "from_email": sender_email.lower(),
            "reply_to_name": _decoded(reply_name),
            "reply_to_email": (reply_email or sender_email).lower(),
            "to": _decoded(message.get("To")),
            "subject": _decoded(message.get("Subject")) or "(No subject)",
            "date": _date_iso(message.get("Date")),
            "message_id": _decoded(message.get("Message-ID")),
            "in_reply_to": _decoded(message.get("In-Reply-To")),
            "references": _decoded(message.get("References")),
            "unread": "\\Seen" not in flags and not mark_seen,
            "body": message_text(message),
            "attachments": [
                {
                    "index": index,
                    "filename": _decoded(part.get_filename()) or f"attachment-{index + 1}",
                    "content_type": part.get_content_type(),
                    "size": len(part.get_payload(decode=True) or b""),
                }
                for index, part in enumerate(attachments)
            ],
        }


def read_attachment(brand: Brand, uid: str, index: int) -> tuple[bytes, str, str]:
    with imap_connection(brand) as connection:
        _, message = _fetch_message(connection, uid)
        attachments = attachment_parts(message)
        if index < 0 or index >= len(attachments):
            raise FileNotFoundError("Attachment not found")
        part = attachments[index]
        return (
            part.get_payload(decode=True) or b"",
            _decoded(part.get_filename()) or f"attachment-{index + 1}",
            part.get_content_type() or "application/octet-stream",
        )


def set_seen(brand: Brand, uid: str, seen: bool) -> None:
    with imap_connection(brand, readonly=False) as connection:
        status, _ = connection.uid("store", str(uid), "+FLAGS" if seen else "-FLAGS", "(\\Seen)")
        if status != "OK":
            raise RuntimeError("The email read status could not be changed")


def build_reply_message(
    brand: Brand,
    profile: BusinessProfile,
    recipient: str,
    subject: str,
    body: str,
    in_reply_to: str | None,
    references: str | None,
) -> EmailMessage:
    username, _ = smtp_credentials(brand)
    if not username:
        raise RuntimeError("SMTP is not configured for this business mailbox")
    message = EmailMessage()
    message_id = make_msgid(domain=username.split("@", 1)[-1])
    message["Message-ID"] = message_id
    message["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    message["From"] = f"{profile.display_name} <{username}>"
    message["To"] = recipient
    message["Reply-To"] = profile.email or username
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        combined = " ".join(item for item in [references, in_reply_to] if item).strip()
        if combined:
            message["References"] = combined[-4000:]
    message.set_content(body)
    assets = BRAND_ASSETS[brand]
    awards = ""
    if brand == Brand.WBM:
        awards = f'''<tr><td style="padding:18px 28px 22px;border-top:1px solid #ece6da;text-align:center;background:#fff">
        <img src="cid:{assets['awards_cid']}" width="300" alt="Weddings By Mark awards" style="display:block;width:100%;max-width:300px;height:auto;margin:0 auto;border:0"></td></tr>'''
    markup = f'''<!doctype html><html><body style="margin:0;background:#f3f1ed;color:#292724">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:22px 10px">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#fff;border:1px solid #e7e2d8;border-radius:14px;overflow:hidden">
    <tr><td align="center" style="padding:22px;background:{assets['soft']};border-bottom:3px solid {assets['accent']}"><img src="cid:{assets['logo_cid']}" alt="{html.escape(profile.display_name)}" style="display:block;max-width:245px;max-height:125px;width:auto;height:auto;margin:auto"></td></tr>
    <tr><td style="padding:30px 32px;font:16px/1.6 Arial,sans-serif;color:#2d2b28">{_body_html(body)}</td></tr>
    <tr><td style="padding:17px 28px;background:#242321;color:#fff;text-align:center;font:12px/1.6 Arial,sans-serif"><strong>{html.escape(profile.display_name)}</strong><br>{html.escape(profile.email or username)}{(' · ' + html.escape(profile.phone)) if profile.phone else ''}</td></tr>
    {awards}</table></td></tr></table></body></html>'''
    message.add_alternative(markup, subtype="html")
    html_part = message.get_payload()[-1]
    for path_key, cid_key in (("logo", "logo_cid"), ("awards", "awards_cid")):
        path: Path | None = assets.get(path_key)
        if path and path.exists():
            html_part.add_related(path.read_bytes(), maintype="image", subtype="png",
                                  cid=f"<{assets[cid_key]}>", filename=path.name,
                                  disposition="inline")
    return message


def _sent_folder(connection: imaplib.IMAP4) -> str | None:
    status, rows = connection.list()
    if status != "OK":
        return None
    for row in rows or []:
        if not isinstance(row, bytes) or b"\\Sent" not in row:
            continue
        quoted = re.search(rb'"((?:[^"\\]|\\.)*)"\s*$', row)
        if quoted:
            return quoted.group(1).decode("utf-8", "replace").replace(r'\"', '"')
        return row.rsplit(b" ", 1)[-1].strip(b'"').decode("utf-8", "replace")
    for candidate in ("Sent", "INBOX.Sent", "Sent Messages"):
        status, _ = connection.status(candidate, "MESSAGES")
        if status == "OK":
            return candidate
    return None


def append_to_sent(brand: Brand, message: EmailMessage) -> bool:
    try:
        with imap_connection(brand, readonly=False) as connection:
            folder = _sent_folder(connection)
            if not folder:
                return False
            status, _ = connection.append(
                folder, "(\\Seen)", imaplib.Time2Internaldate(time.time()), message.as_bytes()
            )
            return status == "OK"
    except Exception:
        return False


def friendly_mail_error(exc: Exception) -> str:
    raw = str(exc) or exc.__class__.__name__
    lowered = raw.lower()
    if "authentication" in lowered or "login" in lowered or "credentials" in lowered:
        return "Mailbox sign-in failed. Check this address and its Hostinger mailbox password in Dockge."
    if "timed out" in lowered or "timeout" in lowered:
        return "Hostinger did not respond in time. Please try Refresh again."
    if "name or service" in lowered or "resolve" in lowered:
        return "The Hostinger mail server could not be reached from TrueNAS."
    return raw[:300]

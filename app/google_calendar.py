"""V8.12 Google Calendar connection and safe one-way booking sync.

BookingSystem2026 remains the source of truth. Calendar errors are recorded
for retry and are never allowed to roll back a booking, form or cancellation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import (Admin, AuditLog, Booking, Brand, DateBlock, Invoice, Payment, Quote,
                     RecordKind, RecordStatus, SystemSetting)
from .security import current_admin

settings = get_settings()

CONNECTION_KEY = "google_calendar_connection"
OAUTH_STATE_KEY = "google_calendar_oauth_state"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarError(RuntimeError):
    pass


def google_calendar_configured() -> bool:
    return bool(settings.google_calendar_client_id and settings.google_calendar_client_secret)


def google_calendar_redirect_uri() -> str:
    return (settings.google_calendar_redirect_uri
            or f"{settings.app_url.rstrip('/')}/api/integrations/google-calendar/callback")


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.session_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_refresh_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_refresh_token(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise GoogleCalendarError(
            "The stored Google connection can no longer be read. Reconnect Google Calendar."
        ) from exc


def _connection(db: Session) -> dict | None:
    row = db.get(SystemSetting, CONNECTION_KEY)
    value = dict(row.value or {}) if row else None
    return value if value and value.get("encrypted_refresh_token") else None


def _save_setting(db: Session, key: str, value: dict) -> None:
    row = db.get(SystemSetting, key)
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))


def _oauth_error(response: httpx.Response, fallback: str) -> GoogleCalendarError:
    try:
        body = response.json()
        detail = body.get("error_description") or body.get("error", {}).get("message") or body.get("error")
    except Exception:
        detail = None
    clean = str(detail or fallback).replace("\n", " ")[:500]
    return GoogleCalendarError(clean)


def _access_token(connection: dict) -> str:
    refresh_token = decrypt_refresh_token(str(connection["encrypted_refresh_token"]))
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "client_id": settings.google_calendar_client_id,
                "client_secret": settings.google_calendar_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=settings.google_calendar_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise GoogleCalendarError("Google Calendar could not be reached. It will be retried safely.") from exc
    if response.status_code >= 400:
        raise _oauth_error(response, "Google Calendar authorization needs attention")
    token = response.json().get("access_token")
    if not token:
        raise GoogleCalendarError("Google did not return an access token. Reconnect Google Calendar.")
    return str(token)


def _booking_calendar_state(booking: Booking) -> dict:
    return dict((booking.workflow_state or {}).get("google_calendar") or {})


def _save_booking_calendar_state(booking: Booking, state: dict) -> None:
    workflow = dict(booking.workflow_state or {})
    workflow["google_calendar"] = state
    booking.workflow_state = workflow


def _accepted_quote(db: Session, booking: Booking) -> bool:
    return db.scalar(select(Quote.id).where(
        Quote.booking_id == booking.id, Quote.status == "accepted"
    ).limit(1)) is not None


def _native_wedding(booking: Booking) -> bool:
    return (
        booking.kind == RecordKind.WEDDING
        and booking.brand == Brand.WBM
        and not booking.legacy_source
        and not booking.is_test
    )


def _should_have_event(db: Session, booking: Booking) -> bool:
    if not _native_wedding(booking) or booking.status == RecordStatus.CANCELLED:
        return False
    # Selecting a package creates a provisional invoice; it does not secure
    # the date. A native wedding reaches Google only after a genuine payment
    # exists. Imported Studio Ninja records are intentionally outside this sync.
    has_payment = db.scalar(select(Payment.id).join(
        Invoice, Invoice.id == Payment.invoice_id
    ).where(Invoice.booking_id == booking.id).limit(1)) is not None
    return bool(
        has_payment
        and booking.status in (
            RecordStatus.CONFIRMED, RecordStatus.IN_PROGRESS, RecordStatus.COMPLETED
        )
    )


def _ceremony_time(booking: Booking) -> str | None:
    raw = str((booking.form_data or {}).get("ceremony_time") or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.strptime(raw[:5], "%H:%M")
    except ValueError:
        return raw[:20]
    return parsed.strftime("%H:%M")


def _first_venue(booking: Booking) -> str:
    data = booking.form_data or {}
    venue = str(booking.venue_or_project or data.get("venue_name") or "").strip()
    if venue:
        return venue[:240]
    ceremony = str(data.get("ceremony_details") or "").strip()
    first_line = ceremony.splitlines()[0].strip() if ceremony else ""
    return first_line[:240] or "Venue to be confirmed"


def _deterministic_event_id(booking: Booking) -> str:
    """A stable Google-safe ID makes retries idempotent even after a timeout."""
    return f"b{hashlib.sha256(booking.id.encode('utf-8')).hexdigest()[:40]}"


def calendar_event_payload(booking: Booking) -> dict:
    if not booking.event_date:
        raise GoogleCalendarError("The wedding date must be set before it can be added to Google Calendar.")
    venue = _first_venue(booking)
    ceremony = _ceremony_time(booking)
    summary_parts = [f"Wedding — {booking.title}", venue]
    if ceremony:
        summary_parts.append(f"Ceremony {ceremony}")
    lines = [
        f"Couple: {booking.title}",
        f"First/main venue: {venue}",
        f"Ceremony time: {ceremony or 'To be confirmed'}",
        f"Package: {booking.package_name or 'To be confirmed'}",
        "",
        f"Booking record: {settings.app_url.rstrip('/')}/bookings/{booking.id}/overview",
        "Managed automatically by BookingSystem2026.",
    ]
    return {
        "id": _deterministic_event_id(booking),
        "summary": " — ".join(summary_parts),
        "description": "\n".join(lines),
        "location": booking.venue_address or venue,
        # Keep this as an all-day wedding rather than inventing photography
        # working hours. The ceremony time remains visible in the title.
        "start": {"date": booking.event_date.isoformat()},
        "end": {"date": (booking.event_date + timedelta(days=1)).isoformat()},
        "transparency": "opaque",
        "extendedProperties": {"private": {
            "booking_system": "BookingSystem2026",
            "booking_id": booking.id,
        }},
    }


def _date_block_calendar_state(block: DateBlock) -> dict:
    return dict(block.google_calendar_state or {})


def _save_date_block_calendar_state(block: DateBlock, state: dict) -> None:
    block.google_calendar_state = state


def _deterministic_date_block_event_id(block: DateBlock) -> str:
    return f"d{hashlib.sha256(block.id.encode('utf-8')).hexdigest()[:40]}"


def date_block_event_payload(block: DateBlock) -> dict:
    """Create one private all-day event for the inclusive blocked period."""
    return {
        "id": _deterministic_date_block_event_id(block),
        "summary": f"Unavailable — {block.label}",
        "description": "\n".join(filter(None, [
            block.notes,
            "",
            "Private availability block managed automatically by BookingSystem2026.",
        ])),
        "start": {"date": block.start_date.isoformat()},
        # Google all-day event end dates are exclusive. The app's end date is
        # inclusive, so add one day here to cover the user's complete range.
        "end": {"date": (block.end_date + timedelta(days=1)).isoformat()},
        "transparency": "opaque",
        "extendedProperties": {"private": {
            "booking_system": "BookingSystem2026",
            "date_block_id": block.id,
        }},
    }


def _calendar_request(method: str, path: str, token: str, *, json: dict | None = None) -> httpx.Response:
    try:
        return httpx.request(
            method,
            f"{CALENDAR_API}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params={"sendUpdates": "none"},
            json=json,
            timeout=settings.google_calendar_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise GoogleCalendarError("Google Calendar could not be reached. It will be retried safely.") from exc


def _record_audit(db: Session, booking: Booking, action: str, details: dict) -> None:
    db.add(AuditLog(action=action, entity_type="booking", entity_id=booking.id, details=details))


def sync_booking_calendar_safely(db: Session, booking: Booking) -> dict:
    """Create, update or remove one event, swallowing all integration failures."""
    current = _booking_calendar_state(booking)
    event_id = current.get("event_id")
    should_exist = _should_have_event(db, booking)
    # A create request can reach Google and then time out before the response is
    # saved locally. If the booking is subsequently cancelled or unsecured, use
    # the same deterministic ID for a harmless delete (Google returns 404 when
    # no event was ever created) so an uncertain remote event cannot survive.
    uncertain_create = (
        current.get("status") in {"pending", "error"}
        and current.get("desired_action") in {"create", "update"}
    )
    if not event_id and not should_exist and uncertain_create:
        event_id = _deterministic_event_id(booking)
    wants_delete = bool(event_id) and (booking.status == RecordStatus.CANCELLED or not should_exist or not booking.event_date)

    if not should_exist and not wants_delete:
        return current

    desired_action = "delete" if wants_delete else ("update" if event_id else "create")
    now = datetime.now(timezone.utc).isoformat()
    connection = _connection(db)
    if not google_calendar_configured() or not connection:
        pending = {**current, "status": "pending_delete" if wants_delete else "pending",
                   "desired_action": desired_action, "last_attempt_at": now,
                   "last_error": "Google Calendar is not connected."}
        _save_booking_calendar_state(booking, pending)
        db.commit()
        return pending

    calendar_id = str(connection.get("calendar_id") or "primary")
    try:
        access_token = _access_token(connection)
        if wants_delete:
            response = _calendar_request(
                "DELETE", f"/calendars/{quote(calendar_id, safe='')}/events/{quote(str(event_id), safe='')}",
                access_token,
            )
            if response.status_code not in (204, 404, 410):
                raise _oauth_error(response, "Google Calendar could not remove the event")
            result = {"status": "removed", "calendar_id": calendar_id,
                      "removed_event_id": event_id, "last_synced_at": now,
                      "last_attempt_at": now, "last_error": None, "desired_action": None}
            _save_booking_calendar_state(booking, result)
            _record_audit(db, booking, "google_calendar_remove", {"event_id": event_id})
        else:
            payload = calendar_event_payload(booking)
            response = None
            action = "create"
            if event_id:
                action = "update"
                response = _calendar_request(
                    "PUT", f"/calendars/{quote(calendar_id, safe='')}/events/{quote(str(event_id), safe='')}",
                    access_token, json=payload,
                )
            if response is None or response.status_code in (404, 410):
                action = "create"
                response = _calendar_request(
                    "POST", f"/calendars/{quote(calendar_id, safe='')}/events",
                    access_token, json=payload,
                )
                # A previous POST can succeed at Google while our server times
                # out before saving the response. The deterministic event ID
                # turns that retry conflict into an update, never a duplicate.
                if response.status_code == 409:
                    action = "update"
                    stable_id = payload["id"]
                    response = _calendar_request(
                        "PUT", f"/calendars/{quote(calendar_id, safe='')}/events/{quote(stable_id, safe='')}",
                        access_token, json=payload,
                    )
            if response.status_code >= 400:
                raise _oauth_error(response, "Google Calendar could not save the event")
            event = response.json()
            result = {"status": "synced", "calendar_id": calendar_id,
                      "event_id": event.get("id") or payload["id"], "html_link": event.get("htmlLink"),
                      "last_synced_at": now, "last_attempt_at": now,
                      "last_error": None, "desired_action": None}
            _save_booking_calendar_state(booking, result)
            _record_audit(db, booking, f"google_calendar_{action}",
                          {"event_id": result.get("event_id"), "ceremony_time": _ceremony_time(booking),
                           "venue": _first_venue(booking)})
        db.commit()
        return result
    except Exception as exc:
        message = str(exc)[:1000] or "Unknown Google Calendar error"
        failed = {**current, "status": "pending_delete" if wants_delete else "error",
                  "calendar_id": calendar_id, "desired_action": desired_action,
                  "last_attempt_at": now, "last_error": message}
        _save_booking_calendar_state(booking, failed)
        _record_audit(db, booking, "google_calendar_error",
                      {"desired_action": desired_action, "error": message})
        db.commit()
        return failed


def sync_date_block_calendar_safely(db: Session, block: DateBlock) -> dict:
    """Create, update or remove a manual availability block without failing its save."""
    current = _date_block_calendar_state(block)
    event_id = current.get("event_id")
    should_exist = block.deleted_at is None
    uncertain_create = (
        current.get("status") in {"pending", "error"}
        and current.get("desired_action") in {"create", "update"}
    )
    if not event_id and not should_exist and uncertain_create:
        event_id = _deterministic_date_block_event_id(block)
    wants_delete = bool(event_id) and not should_exist
    if not should_exist and not wants_delete:
        return current

    desired_action = "delete" if wants_delete else ("update" if event_id else "create")
    attempted_at = datetime.now(timezone.utc).isoformat()
    connection = _connection(db)
    if not google_calendar_configured() or not connection:
        pending = {
            **current,
            "status": "pending_delete" if wants_delete else "pending",
            "desired_action": desired_action,
            "last_attempt_at": attempted_at,
            "last_error": "Google Calendar is not connected.",
        }
        _save_date_block_calendar_state(block, pending)
        db.commit()
        return pending

    calendar_id = str(connection.get("calendar_id") or "primary")
    try:
        access_token = _access_token(connection)
        if wants_delete:
            response = _calendar_request(
                "DELETE",
                f"/calendars/{quote(calendar_id, safe='')}/events/{quote(str(event_id), safe='')}",
                access_token,
            )
            if response.status_code not in (204, 404, 410):
                raise _oauth_error(response, "Google Calendar could not remove the blocked period")
            result = {
                "status": "removed",
                "calendar_id": calendar_id,
                "removed_event_id": event_id,
                "last_synced_at": attempted_at,
                "last_attempt_at": attempted_at,
                "last_error": None,
                "desired_action": None,
            }
            action = "remove"
        else:
            payload = date_block_event_payload(block)
            response = None
            action = "create"
            if event_id:
                action = "update"
                response = _calendar_request(
                    "PUT",
                    f"/calendars/{quote(calendar_id, safe='')}/events/{quote(str(event_id), safe='')}",
                    access_token,
                    json=payload,
                )
            if response is None or response.status_code in (404, 410):
                action = "create"
                response = _calendar_request(
                    "POST",
                    f"/calendars/{quote(calendar_id, safe='')}/events",
                    access_token,
                    json=payload,
                )
                if response.status_code == 409:
                    action = "update"
                    response = _calendar_request(
                        "PUT",
                        f"/calendars/{quote(calendar_id, safe='')}/events/{quote(payload['id'], safe='')}",
                        access_token,
                        json=payload,
                    )
            if response.status_code >= 400:
                raise _oauth_error(response, "Google Calendar could not save the blocked period")
            event = response.json()
            result = {
                "status": "synced",
                "calendar_id": calendar_id,
                "event_id": event.get("id") or payload["id"],
                "html_link": event.get("htmlLink"),
                "last_synced_at": attempted_at,
                "last_attempt_at": attempted_at,
                "last_error": None,
                "desired_action": None,
            }
        _save_date_block_calendar_state(block, result)
        db.add(AuditLog(
            action=f"google_calendar_date_block_{action}",
            entity_type="date_block",
            entity_id=block.id,
            details={
                "event_id": result.get("event_id") or result.get("removed_event_id"),
                "start_date": block.start_date.isoformat(),
                "end_date": block.end_date.isoformat(),
            },
        ))
        db.commit()
        return result
    except Exception as exc:
        message = str(exc)[:1000] or "Unknown Google Calendar error"
        failed = {
            **current,
            "status": "pending_delete" if wants_delete else "error",
            "calendar_id": calendar_id,
            "desired_action": desired_action,
            "last_attempt_at": attempted_at,
            "last_error": message,
        }
        _save_date_block_calendar_state(block, failed)
        db.add(AuditLog(
            action="google_calendar_date_block_error",
            entity_type="date_block",
            entity_id=block.id,
            details={"desired_action": desired_action, "error": message},
        ))
        db.commit()
        return failed


def retry_pending_calendar_syncs(db: Session) -> dict:
    """Retry only previously pending/failed one-way calendar work."""
    if not google_calendar_configured() or not _connection(db):
        return {"checked": 0, "synced": 0, "removed": 0, "failed": 0}
    rows = db.scalars(select(Booking).where(
        Booking.brand == Brand.WBM,
        Booking.kind == RecordKind.WEDDING,
        Booking.legacy_source.is_(None),
        Booking.is_test.is_(False),
    )).all()
    candidates = [row for row in rows if _booking_calendar_state(row).get("status") in {
        "pending", "pending_delete", "error",
    }]
    block_rows = db.scalars(select(DateBlock)).all()
    block_candidates = [row for row in block_rows if _date_block_calendar_state(row).get("status") in {
        "pending", "pending_delete", "error",
    }]
    results = [sync_booking_calendar_safely(db, row) for row in candidates]
    results.extend(sync_date_block_calendar_safely(db, row) for row in block_candidates)
    return {
        "checked": len(results),
        "synced": sum(row.get("status") == "synced" for row in results),
        "removed": sum(row.get("status") == "removed" for row in results),
        "failed": sum(row.get("status") in {"pending", "pending_delete", "error"}
                      for row in results),
    }


def google_calendar_status(db: Session) -> dict:
    connection = _connection(db)
    bookings = db.scalars(select(Booking).where(Booking.kind == RecordKind.WEDDING)).all()
    blocks = db.scalars(select(DateBlock)).all()
    states = [_booking_calendar_state(item) for item in bookings]
    block_states = [_date_block_calendar_state(item) for item in blocks]
    problems = [
        {"booking_id": booking.id, "title": booking.title,
         "status": state.get("status"), "error": state.get("last_error")}
        for booking, state in zip(bookings, states)
        if state.get("status") in ("error", "pending", "pending_delete")
    ]
    problems.extend([
        {"date_block_id": block.id, "title": block.label,
         "status": state.get("status"), "error": state.get("last_error")}
        for block, state in zip(blocks, block_states)
        if state.get("status") in ("error", "pending", "pending_delete")
    ])
    all_states = states + block_states
    return {
        "configured": google_calendar_configured(),
        "connected": bool(connection),
        "calendar": "Primary Google Calendar",
        "redirect_uri": google_calendar_redirect_uri(),
        "synced": sum(state.get("status") == "synced" for state in all_states),
        "pending": sum(state.get("status") in ("pending", "pending_delete") for state in all_states),
        "errors": sum(state.get("status") == "error" for state in all_states),
        "problems": problems[:20],
        "connected_at": connection.get("connected_at") if connection else None,
    }


def register_google_calendar_routes(app: FastAPI) -> None:
    @app.get("/api/integrations/google-calendar/status")
    def status_route(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
        return google_calendar_status(db)

    @app.get("/api/integrations/google-calendar/connect")
    def connect_route(admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
        if not google_calendar_configured():
            raise HTTPException(503, "Add the Google Calendar Client ID and Client Secret to the app environment first.")
        state = secrets.token_urlsafe(32)
        _save_setting(db, OAUTH_STATE_KEY, {
            "state_hash": hashlib.sha256(state.encode("utf-8")).hexdigest(),
            "admin_id": admin.id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        })
        db.commit()
        params = {
            "client_id": settings.google_calendar_client_id,
            "redirect_uri": google_calendar_redirect_uri(),
            "response_type": "code",
            "scope": CALENDAR_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return {"authorization_url": f"{AUTH_URL}?{urlencode(params)}"}

    @app.get("/api/integrations/google-calendar/callback")
    def callback_route(state: str = Query(""), code: str = Query(""), error: str = Query(""),
                       db: Session = Depends(get_db)):
        target = f"{settings.app_url.rstrip('/')}/settings"
        state_row = db.get(SystemSetting, OAUTH_STATE_KEY)
        expected = dict(state_row.value or {}) if state_row else {}
        expires_at = expected.get("expires_at")
        valid = bool(
            state and expected.get("state_hash")
            and hmac.compare_digest(hashlib.sha256(state.encode("utf-8")).hexdigest(), expected["state_hash"])
        )
        try:
            valid = valid and datetime.fromisoformat(str(expires_at)) > datetime.now(timezone.utc)
        except (TypeError, ValueError):
            valid = False
        if state_row:
            db.delete(state_row)
            db.commit()
        if error:
            return RedirectResponse(f"{target}?google_calendar=denied", status_code=303)
        if not valid or not code:
            return RedirectResponse(f"{target}?google_calendar=invalid", status_code=303)
        try:
            response = httpx.post(TOKEN_URL, data={
                "code": code,
                "client_id": settings.google_calendar_client_id,
                "client_secret": settings.google_calendar_client_secret,
                "redirect_uri": google_calendar_redirect_uri(),
                "grant_type": "authorization_code",
            }, timeout=settings.google_calendar_timeout_seconds)
            if response.status_code >= 400:
                raise _oauth_error(response, "Google rejected the connection")
            token = response.json()
            refresh_token = token.get("refresh_token")
            if not refresh_token:
                raise GoogleCalendarError("Google did not return a refresh token. Remove access in Google and reconnect.")
            _save_setting(db, CONNECTION_KEY, {
                "encrypted_refresh_token": encrypt_refresh_token(str(refresh_token)),
                "calendar_id": "primary",
                "scope": token.get("scope") or CALENDAR_SCOPE,
                "connected_at": datetime.now(timezone.utc).isoformat(),
            })
            db.add(AuditLog(action="google_calendar_connect", entity_type="system_setting",
                            entity_id=CONNECTION_KEY, details={"calendar_id": "primary"}))
            db.commit()
            return RedirectResponse(f"{target}?google_calendar=connected", status_code=303)
        except Exception:
            db.rollback()
            return RedirectResponse(f"{target}?google_calendar=error", status_code=303)

    @app.post("/api/integrations/google-calendar/disconnect")
    def disconnect_route(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
        row = db.get(SystemSetting, CONNECTION_KEY)
        if row:
            db.delete(row)
        db.add(AuditLog(action="google_calendar_disconnect", entity_type="system_setting",
                        entity_id=CONNECTION_KEY, details={"existing_events_retained": True}))
        db.commit()
        return {"ok": True, "message": "Google Calendar disconnected. Existing events were left unchanged."}

    @app.post("/api/integrations/google-calendar/sync")
    def sync_all_route(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
        if not _connection(db):
            raise HTTPException(409, "Connect Google Calendar before syncing bookings.")
        bookings = db.scalars(select(Booking).where(Booking.kind == RecordKind.WEDDING)).all()
        results = []
        for booking in bookings:
            before = _booking_calendar_state(booking)
            if _should_have_event(db, booking) or before.get("event_id"):
                results.append(sync_booking_calendar_safely(db, booking))
        blocks = db.scalars(select(DateBlock)).all()
        for block in blocks:
            before = _date_block_calendar_state(block)
            if block.deleted_at is None or before.get("event_id") or before.get("status") in {
                "pending", "pending_delete", "error",
            }:
                results.append(sync_date_block_calendar_safely(db, block))
        return {
            "ok": True,
            "checked": len(results),
            "synced": sum(item.get("status") == "synced" for item in results),
            "removed": sum(item.get("status") == "removed" for item in results),
            "needs_attention": sum(item.get("status") in ("error", "pending", "pending_delete") for item in results),
        }

    @app.post("/api/bookings/{booking_id}/google-calendar-sync")
    def sync_one_route(booking_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
        booking = db.get(Booking, booking_id)
        if not booking:
            raise HTTPException(404, "Record not found")
        return sync_booking_calendar_safely(db, booking)

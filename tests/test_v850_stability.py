from datetime import date, datetime, timezone
from pathlib import Path
import struct

import pytest
from pydantic import ValidationError

from app.business_time import (automatic_delivery_allowed,
                               automatic_delivery_window_label,
                               business_date, business_today)
from app.config import Settings


ROOT = Path(__file__).parents[1]


def test_uk_business_date_handles_bst_midnight_correctly():
    assert business_today(datetime(2026, 6, 1, 22, 59, tzinfo=timezone.utc)) == date(2026, 6, 1)
    assert business_today(datetime(2026, 6, 1, 23, 1, tzinfo=timezone.utc)) == date(2026, 6, 2)
    assert business_date(datetime(2026, 12, 1, 23, 1, tzinfo=timezone.utc)) == date(2026, 12, 1)


def test_automatic_client_messages_are_limited_to_uk_daytime_in_summer_and_winter():
    # BST is UTC+1: 08:00 UTC is 09:00 in Manchester.
    assert not automatic_delivery_allowed(9, 19, now=datetime(2026, 6, 1, 7, 59, tzinfo=timezone.utc))
    assert automatic_delivery_allowed(9, 19, now=datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc))
    assert not automatic_delivery_allowed(9, 19, now=datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc))
    # GMT is UTC: the same rule remains 09:00-19:00 local time in winter.
    assert automatic_delivery_allowed(9, 19, now=datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc))
    assert not automatic_delivery_allowed(9, 19, now=datetime(2026, 12, 1, 19, 0, tzinfo=timezone.utc))
    assert automatic_delivery_allowed(0, 24, now=datetime(2026, 12, 1, 23, 59, tzinfo=timezone.utc))
    assert automatic_delivery_window_label(9, 19) == "09:00-19:00 Europe/London"


def test_invalid_automatic_message_window_is_rejected():
    with pytest.raises(ValidationError, match="must be later"):
        Settings(_env_file=None, automatic_message_start_hour=19, automatic_message_end_hour=9)


def test_known_default_admin_password_is_rejected_in_production():
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD"):
        Settings(
            _env_file=None,
            app_env="production",
            session_secret="s" * 40,
            admin_password="ChangeMeNow!123",
            database_url="postgresql+psycopg://bookingapp:real-secret@database/bookingapp",
        )


def test_v850_release_keeps_manual_messages_available_and_automations_off_by_default():
    settings = Settings(_env_file=None)
    assert settings.automatic_message_start_hour == 9
    assert settings.automatic_message_end_hour == 19
    assert settings.sms_automatic_enabled is False
    assert settings.reminders_enabled is False
    sms_routes = (ROOT / "app" / "sms_routes.py").read_text()
    main = (ROOT / "app" / "main.py").read_text()
    assert "and within_window" in sms_routes
    assert "and within_window" in main
    assert "def run_due_sms_automations" in sms_routes
    assert "def run_reminders_now" in main


def test_v850_recovery_catalog_uses_current_platinum_and_ultimate_prices():
    bootstrap = (ROOT / "app" / "bootstrap.py").read_text()
    assert '("platinum", "Platinum Package 4 2026/27/28", 1350, 150' in bootstrap
    assert '("ultimate", "Ultimate Package 2026/27/28", 1799, 150' in bootstrap
    assert '("platinum", "Platinum Package 4 2026/27/28", 1299, 150' not in bootstrap
    assert '("ultimate", "Ultimate Package 2026/27/28", 1699, 150' not in bootstrap


def test_v850_build_identity_and_visible_safety_window():
    index = (ROOT / "app" / "static" / "index.html").read_text()
    sms_js = (ROOT / "app" / "static" / "v849.js").read_text()
    backup = (ROOT / "app" / "backup.py").read_text()
    assert "BOOKINGSYSTEM2026 · COMPLETE V8.50" in index
    assert 'BACKUP_BUILD = "2026.09.16-stability-v8.50"' in backup
    assert "09:00-19:00 Europe/London" in sms_js
    assert "manual sends remain available" in sms_js


def test_approved_awards_panel_is_email_safe_and_keeps_expected_dimensions():
    awards = ROOT / "app" / "static" / "branding" / "weddings-by-mark-awards.png"
    data = awards.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (1020, 680)
    assert len(data) < 300_000

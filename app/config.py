from functools import lru_cache
from datetime import date
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Mark's Business Studio"
    app_env: str = "development"
    app_url: str = "http://localhost:30049"
    session_secret: str = Field(default="development-only-change-me-please-123456")
    admin_email: str = "mark@example.com"
    admin_password: str = "ChangeMeNow!123"
    database_url: str = "sqlite:///./bookingapp.db"
    storage_root: Path = Path("./storage")
    cookie_secure: bool = False
    session_hours: int = 12
    max_upload_mb: int = 25
    invoice_start: int = 2000
    seed_demo_data: bool = False
    smtp_host: str = "smtp.hostinger.com"
    smtp_port: int = 465
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_wbm_username: str | None = "mark@perfectweddingsbymark.uk"
    smtp_wbm_password: str | None = None
    smtp_ivory_username: str | None = "admin@ivorydigital.uk"
    smtp_ivory_password: str | None = None
    smtp_use_ssl: bool = True
    imap_host: str = "imap.hostinger.com"
    imap_port: int = 993
    imap_wbm_username: str | None = None
    imap_wbm_password: str | None = None
    imap_ivory_username: str | None = None
    imap_ivory_password: str | None = None
    imap_use_ssl: bool = True
    mail_timeout_seconds: int = Field(default=20, ge=5, le=60)
    mail_list_limit: int = Field(default=60, ge=10, le=200)
    reminder_scan_hours: int = 6
    reminders_enabled: bool = False
    email_retry_minutes: int = Field(default=60, ge=5, le=1440)
    automatic_message_start_hour: int = Field(default=9, ge=0, le=23)
    automatic_message_end_hour: int = Field(default=19, ge=1, le=24)
    sms_enabled: bool = False
    sms_automatic_enabled: bool = False
    sms_api_url: str = "https://api.thesmsworks.co.uk/v1"
    sms_api_token: str | None = None
    sms_sender_id: str = "WedsByMark"
    sms_reply_number: str | None = None
    sms_webhook_username: str | None = None
    sms_webhook_password: str | None = None
    sms_test_number: str | None = None
    sms_timeout_seconds: int = Field(default=20, ge=5, le=60)
    sms_scan_hours: int = Field(default=6, ge=1, le=24)
    login_max_failures: int = Field(default=5, ge=3, le=20)
    login_failure_window_minutes: int = Field(default=15, ge=5, le=120)
    login_lock_minutes: int = Field(default=15, ge=5, le=1440)
    google_maps_api_key: str | None = None
    google_calendar_client_id: str | None = None
    google_calendar_client_secret: str | None = None
    google_calendar_redirect_uri: str | None = None
    google_calendar_timeout_seconds: int = Field(default=20, ge=5, le=60)
    google_calendar_retry_minutes: int = Field(default=30, ge=5, le=1440)
    accounts_integration_enabled: bool = False
    accounts_integration_auto_sync: bool = False
    accounts_api_url: str | None = None
    accounts_integration_key: str | None = None
    accounts_sync_minutes: int = Field(default=10, ge=2, le=1440)
    growth_integration_enabled: bool = False
    growth_integration_auto_sync: bool = False
    growth_api_url: str | None = None
    growth_integration_key: str | None = None
    growth_sync_minutes: int = Field(default=5, ge=1, le=1440)
    growth_sync_from_date: date | None = date(2026, 9, 7)

    @model_validator(mode="after")
    def reject_placeholder_production_secrets(self):
        if self.automatic_message_end_hour <= self.automatic_message_start_hour:
            raise ValueError("AUTOMATIC_MESSAGE_END_HOUR must be later than AUTOMATIC_MESSAGE_START_HOUR")
        if self.app_env.lower() == "production":
            if len(self.session_secret) < 32 or "replace" in self.session_secret.lower():
                raise ValueError("SESSION_SECRET must be replaced with at least 32 random characters")
            weak_admin_passwords = {
                "changemenow!123", "change-me-now", "password123!",
                "replace-with-a-long-unique-password",
            }
            if (len(self.admin_password) < 12
                    or "replace" in self.admin_password.lower()
                    or "changeme" in self.admin_password.lower()
                    or self.admin_password.lower() in weak_admin_passwords):
                raise ValueError("ADMIN_PASSWORD must be replaced with a strong unique password")
            if "replace" in self.database_url.lower():
                raise ValueError("DATABASE_URL must contain the real database password")
            if self.accounts_integration_enabled:
                if not self.accounts_api_url or not self.accounts_api_url.startswith(("http://", "https://")):
                    raise ValueError("ACCOUNTS_API_URL must be a complete http:// or https:// address")
                if not self.accounts_integration_key or len(self.accounts_integration_key) < 32:
                    raise ValueError("ACCOUNTS_INTEGRATION_KEY must contain at least 32 characters")
            if self.growth_integration_enabled:
                if not self.growth_api_url or not self.growth_api_url.startswith(("http://", "https://")):
                    raise ValueError("GROWTH_API_URL must be a complete http:// or https:// address")
                if not self.growth_integration_key or len(self.growth_integration_key) < 32:
                    raise ValueError("GROWTH_INTEGRATION_KEY must contain at least 32 characters")
            if self.sms_automatic_enabled and not self.sms_enabled:
                raise ValueError("SMS_AUTOMATIC_ENABLED requires SMS_ENABLED=true")
            if self.sms_enabled:
                if not self.sms_api_url.startswith("https://"):
                    raise ValueError("SMS_API_URL must use https://")
                if not self.sms_api_token or len(self.sms_api_token) < 20:
                    raise ValueError("SMS_API_TOKEN must contain the JSON Web Token from The SMS Works")
                sender = (self.sms_reply_number or self.sms_sender_id or "").strip()
                if sender.isdigit():
                    if not 3 <= len(sender) <= 15:
                        raise ValueError("SMS reply number must contain 3 to 15 digits")
                elif not (4 <= len(sender) <= 11 and sender.isalnum()):
                    raise ValueError("SMS_SENDER_ID must be 4 to 11 letters/numbers with no spaces")
                if bool(self.sms_webhook_username) != bool(self.sms_webhook_password):
                    raise ValueError("SMS webhook username and password must be set together")
                if self.sms_webhook_password and len(self.sms_webhook_password) < 16:
                    raise ValueError("SMS_WEBHOOK_PASSWORD must contain at least 16 characters")
                if self.sms_reply_number and not (
                    self.sms_webhook_username and self.sms_webhook_password
                ):
                    raise ValueError("SMS reply webhooks require a username and password")
            if bool(self.google_calendar_client_id) != bool(self.google_calendar_client_secret):
                raise ValueError("GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET must be set together")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

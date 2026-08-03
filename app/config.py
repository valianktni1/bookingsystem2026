from functools import lru_cache
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

    @model_validator(mode="after")
    def reject_placeholder_production_secrets(self):
        if self.app_env.lower() == "production":
            if len(self.session_secret) < 32 or "replace" in self.session_secret.lower():
                raise ValueError("SESSION_SECRET must be replaced with at least 32 random characters")
            if len(self.admin_password) < 12 or "replace" in self.admin_password.lower():
                raise ValueError("ADMIN_PASSWORD must be replaced with a strong unique password")
            if "replace" in self.database_url.lower():
                raise ValueError("DATABASE_URL must contain the real database password")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

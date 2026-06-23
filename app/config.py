"""
config.py — Centralised settings loaded from environment variables.
Never hardcode secrets. All sensitive values come from .env / platform env.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Bot ───────────────────────────────────────────────────────────
    bot_token: str = Field(..., description="Telegram bot token")
    webhook_secret: str = Field(..., description="Webhook secret token")
    webhook_host: str = Field("", description="Primary webhook host (Railway)")
    webhook_path: str = Field("/webhook", description="Webhook path")
    backup_url: str = Field("", description="Render backup base URL")

    # ── Owner ─────────────────────────────────────────────────────────
    owner_id: int = Field(..., description="Telegram user_id of the bot owner")

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = Field(..., description="asyncpg PostgreSQL DSN")

    # ── Redis (optional) ─────────────────────────────────────────────
    redis_url: Optional[str] = Field(None, description="Redis DSN (optional)")

    # ── Rate limiting ─────────────────────────────────────────────────
    rate_limit_per_minute: int = Field(10)
    rate_limit_per_day: int = Field(200)

    # ── App ───────────────────────────────────────────────────────────
    environment: str = Field("production")
    log_level: str = Field("INFO")
    max_history_per_user: int = Field(50)
    default_watermark_text: str = Field("@myqrro_bot")
    watermark_enabled: bool = Field(True)

    # ── Computed helpers ──────────────────────────────────────────────
    @property
    def webhook_url(self) -> str:
        host = self.webhook_host.rstrip("/")
        path = self.webhook_path.lstrip("/")
        return f"{host}/{path}/{self.webhook_secret}"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith(("postgresql+asyncpg://", "postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL DSN")
        # Normalise postgres:// → postgresql+asyncpg://
        v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()

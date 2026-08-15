import os
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TG_BOT_TOKEN: SecretStr
    TG_ADMIN_CHAT_ID: int
    TG_ADMIN_USER_ID: int | None = None
    DB_PATH: str = "data/bot.db"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    BOT_LANGUAGE: Literal["zh", "en"] = "zh"
    DISPLAY_TIMEZONE: str = "Asia/Shanghai"

    # Hyperliquid endpoints (configurable, no longer hardcoded)
    HL_API_URL: str = "https://api.hyperliquid.xyz/info"
    HL_WS_URL: str = "wss://api.hyperliquid.xyz/ws"

    # Monitor tuning
    FILL_BUFFER_SECONDS: float = 1.0
    ORDER_BUFFER_SECONDS: float = 2.0
    OUTBOX_POLL_SECONDS: float = 1.0
    OUTBOX_RETRY_MAX_SECONDS: float = 300.0
    MAX_WS_USERS: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalise_log_level(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("BOT_LANGUAGE", mode="before")
    @classmethod
    def _normalise_language(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator(
        "FILL_BUFFER_SECONDS",
        "ORDER_BUFFER_SECONDS",
        "OUTBOX_POLL_SECONDS",
        "OUTBOX_RETRY_MAX_SECONDS",
    )
    @classmethod
    def _positive_buffer_window(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("buffer window must be greater than zero")
        return v

    @field_validator("MAX_WS_USERS")
    @classmethod
    def _valid_ws_user_limit(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError(
                "MAX_WS_USERS must be between 1 and Hyperliquid's limit of 10"
            )
        return v

    @field_validator("DISPLAY_TIMEZONE")
    @classmethod
    def _valid_timezone(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {v}") from exc
        return v

    @field_validator("DB_PATH", mode="after")
    @classmethod
    def _ensure_db_dir(cls, v: str) -> str:
        """Ensure the parent directory for the database file exists."""
        parent = Path(v).parent
        if parent != Path(".") and parent != Path(""):
            os.makedirs(parent, exist_ok=True)
        return v


settings = Settings()

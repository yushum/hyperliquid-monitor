import os
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    TG_BOT_TOKEN: SecretStr
    TG_ADMIN_CHAT_ID: int
    DB_PATH: str = "data/bot.db"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    BOT_LANGUAGE: str = "zh"

    # Hyperliquid endpoints (configurable, no longer hardcoded)
    HL_API_URL: str = "https://api.hyperliquid.xyz/info"
    HL_WS_URL: str = "wss://api.hyperliquid.xyz/ws"

    # Monitor tuning
    FILL_BUFFER_SECONDS: float = 1.0
    ORDER_BUFFER_SECONDS: float = 2.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalise_log_level(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("DB_PATH", mode="after")
    @classmethod
    def _ensure_db_dir(cls, v: str) -> str:
        """Ensure the parent directory for the database file exists."""
        parent = Path(v).parent
        if parent != Path(".") and parent != Path(""):
            os.makedirs(parent, exist_ok=True)
        return v


settings = Settings()

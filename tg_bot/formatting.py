"""Formatting helpers shared by Telegram handlers and monitor notifications."""

from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.config import settings


def escape_html(value: Any) -> str:
    """Escape dynamic text before inserting it into a Telegram HTML message."""
    return escape(str(value), quote=False) if value is not None else ""


def format_timestamp(timestamp_ms: Any, lang_code: str = "zh") -> str:
    """Format a millisecond timestamp in the configured display timezone."""
    try:
        timestamp = int(timestamp_ms)
        if timestamp <= 0:
            raise ValueError
        timezone = ZoneInfo(settings.DISPLAY_TIMEZONE)
        value = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone)
    except (TypeError, ValueError, OSError, OverflowError, ZoneInfoNotFoundError):
        return "未知时间" if lang_code and "zh" in lang_code.lower() else "Unknown time"
    return f"{value:%Y-%m-%d %H:%M:%S} {value.tzname() or settings.DISPLAY_TIMEZONE}"


def unavailable(lang_code: str = "zh") -> str:
    return (
        "接口未提供"
        if lang_code and "zh" in lang_code.lower()
        else "Not provided by API"
    )


def split_message(text: str, max_length: int = 4000) -> list[str]:
    """Split a Telegram message without producing empty or oversized chunks."""
    if max_length <= 0:
        raise ValueError("max_length must be greater than zero")
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        pieces = [
            paragraph[start : start + max_length]
            for start in range(0, max(len(paragraph), 1), max_length)
        ]
        for piece in pieces:
            separator = "\n\n" if current else ""
            if len(current) + len(separator) + len(piece) <= max_length:
                current += separator + piece
                continue
            if current:
                chunks.append(current)
            current = piece
    if current or not chunks:
        chunks.append(current)
    return chunks

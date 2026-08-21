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
    offset = value.strftime("%z")
    offset_display = f"UTC{offset[:3]}:{offset[3:]}" if offset else settings.DISPLAY_TIMEZONE
    return f"{value:%Y-%m-%d %H:%M:%S} {offset_display}"


def unavailable(lang_code: str = "zh") -> str:
    return (
        "接口未提供"
        if lang_code and "zh" in lang_code.lower()
        else "Not provided by API"
    )


def format_address_display(
    address: Any, note: Any = None, lang_code: str = "zh"
) -> str:
    """Format an address with an optional remark for clean HTML display."""
    if not address:
        return (
            "<i>未知</i>"
            if lang_code and "zh" in lang_code.lower()
            else "<i>Unknown</i>"
        )
    addr_str = str(address).strip()
    if addr_str in ("无法确定 (监控了多个地址)", "Unknown (multiple addresses)"):
        return f"<i>{escape_html(addr_str)}</i>"
    if note and str(note).strip():
        return f"<b>{escape_html(str(note).strip())}</b> (<code>{escape_html(addr_str)}</code>)"
    return f"<code>{escape_html(addr_str)}</code>"


def format_notification_address(
    address: Any, note: Any = None, lang_code: str = "zh"
) -> str:
    """Render a compact wallet identity for glanceable notifications."""
    if not address:
        return format_address_display(address, note, lang_code)
    addr_str = str(address).strip()
    short = (
        f"{addr_str[:6]}…{addr_str[-4:]}" if len(addr_str) > 14 else addr_str
    )
    if note and str(note).strip():
        return f"<b>{escape_html(str(note).strip())}</b> · <code>{escape_html(short)}</code>"
    return f"<code>{escape_html(short)}</code>"


def format_usd(amount: Any, show_sign: bool = False, decimals: int = 2) -> str:
    """Format a monetary USD value with commas and fixed decimals."""
    try:
        val = float(amount)
    except (TypeError, ValueError):
        val = 0.0
    if show_sign:
        if val > 0.000001:
            return f"+${val:,.{decimals}f}"
        if val < -0.000001:
            return f"-${abs(val):,.{decimals}f}"
    return f"${val:,.{decimals}f}"


def format_price(price: Any) -> str:
    """Format asset price with smart precision based on magnitude."""
    try:
        val = float(price)
    except (TypeError, ValueError):
        val = 0.0
    if val <= 0:
        return "$0.00"
    if val >= 100:
        return f"${val:,.2f}"
    if val >= 1:
        s = f"{val:,.4f}"
        parts = s.split(".")
        if len(parts) == 2:
            dec = parts[1].rstrip("0")
            if len(dec) < 2:
                dec = dec.ljust(2, "0")
            return f"${parts[0]}.{dec}"
        return f"${s}"
    s = f"{val:,.6f}"
    parts = s.split(".")
    if len(parts) == 2:
        dec = parts[1].rstrip("0")
        if len(dec) < 4:
            dec = dec.ljust(4, "0")
        return f"${parts[0]}.{dec}"
    return f"${s}"


def format_crypto_amount(amount: Any, max_decimals: int = 4) -> str:
    """Format token/position size cleanly without unnecessary trailing zeros."""
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return "0"
    if val == 0:
        return "0"
    if val == int(val) and abs(val) >= 1:
        return f"{int(val):,}"
    s = f"{val:,.{max_decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def format_pnl(pnl: Any, lang_code: str = "zh") -> str:
    """Format realized PnL with colored badge and clear sign."""
    try:
        val = float(pnl)
    except (TypeError, ValueError):
        val = 0.0
    if val > 0.0001:
        return f"🟢 <code>+${val:,.2f}</code>"
    if val < -0.0001:
        return f"🔴 <code>-${abs(val):,.2f}</code>"
    return "<code>$0.00</code>"


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

import abc
import asyncio
import logging
import re

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramEntityTooLarge,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)

logger = logging.getLogger(__name__)

# Pre-compiled pattern for stripping HTML tags from log output.
_HTML_TAG_RE = re.compile(r"<[^>]+>")


class PermanentNotificationError(RuntimeError):
    """Telegram rejected a message in a way that retries cannot repair."""


class BaseNotifier(abc.ABC):
    @abc.abstractmethod
    async def notify(self, message: str) -> bool:
        """Send a message and return whether delivery succeeded."""


class TelegramNotifier(BaseNotifier):
    """Sends notifications via Telegram with automatic retry on rate-limits."""

    MAX_RETRIES = 3

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self.bot = bot
        self.chat_id = chat_id

    async def notify(self, message: str) -> bool:
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id, text=message, parse_mode="HTML"
                )
                # Strip HTML tags for readable log output.
                plain = _HTML_TAG_RE.sub("", message)
                logger.info("Notification sent to TG: %s", plain[:80])
                return True
            except TelegramRetryAfter as e:
                logger.warning(
                    "TG rate-limited, retry after %ss (attempt %d/%d)",
                    e.retry_after,
                    attempt,
                    self.MAX_RETRIES,
                )
                await asyncio.sleep(e.retry_after)
            except (TelegramNetworkError, TelegramServerError):
                logger.warning(
                    "Transient TG error (attempt %d/%d).",
                    attempt,
                    self.MAX_RETRIES,
                    exc_info=True,
                )
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(2 ** (attempt - 1))
            except (
                TelegramBadRequest,
                TelegramEntityTooLarge,
                TelegramForbiddenError,
                TelegramNotFound,
                TelegramUnauthorizedError,
            ) as exc:
                raise PermanentNotificationError(str(exc)) from exc
            except Exception:
                logger.exception("Failed to send TG notification.")
                return False
        logger.error(
            "Telegram delivery attempt exhausted; the durable outbox will retry it."
        )
        return False

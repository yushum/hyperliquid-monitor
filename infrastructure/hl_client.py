import logging
from typing import Any

import aiohttp
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from core.config import settings

logger = logging.getLogger(__name__)


class HyperliquidAPIError(Exception):
    """Raised when the Hyperliquid API returns a non-2xx response."""

    def __init__(self, status: int, body: str, user_address: str = "") -> None:
        self.status = status
        self.body = body
        self.user_address = user_address
        detail = f"address={user_address}" if user_address else ""
        super().__init__(f"Hyperliquid API {status} ({detail}): {body[:200]}")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (aiohttp.ClientError, TimeoutError)):
        return True
    return isinstance(exc, HyperliquidAPIError) and (
        exc.status == 429 or 500 <= exc.status < 600
    )


class HyperliquidClient:
    """Hyperliquid Info API client with shared aiohttp session lifecycle."""

    def __init__(self, api_url: str | None = None) -> None:
        self.api_url = api_url or settings.HL_API_URL
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        """Create the shared aiohttp session. Call once at application startup."""
        self._session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30),
        )
        logger.info("HyperliquidClient session created.")

    async def close(self) -> None:
        """Close the shared aiohttp session. Call once at application shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("HyperliquidClient session closed.")

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError(
                "HyperliquidClient session is not started. Call start() first."
            )
        return self._session

    async def _post(self, payload: dict[str, Any], user_address: str = "") -> Any:
        """Send a POST request and return parsed JSON, raising on errors."""
        session = self._ensure_session()
        async with session.post(self.api_url, json=payload) as response:
            if response.status != 200:
                body = await response.text()
                raise HyperliquidAPIError(response.status, body, user_address)
            return await response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def get_clearinghouse_state(self, user_address: str) -> dict[str, Any]:
        """Fetches the clearinghouse state (margin, positions) for an address."""
        payload = {
            "type": "clearinghouseState",
            "user": user_address,
        }
        return await self._post(payload, user_address)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def get_open_orders(self, user_address: str) -> list[dict[str, Any]]:
        """Fetch open orders with the descriptive fields used by the UI."""
        payload = {
            "type": "frontendOpenOrders",
            "user": user_address,
        }
        data = await self._post(payload, user_address)
        return data if isinstance(data, list) else []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def get_portfolio(self, user_address: str) -> list[Any]:
        """Fetches the historical portfolio stats (PnL, equity curve) for an address."""
        payload = {
            "type": "portfolio",
            "user": user_address,
        }
        data = await self._post(payload, user_address)
        return data if isinstance(data, list) else []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def get_order_status(
        self, user_address: str, oid: int | str
    ) -> dict[str, Any] | None:
        """Fetch a full order record, including type/TIF fields when available."""
        payload = {"type": "orderStatus", "user": user_address, "oid": oid}
        data = await self._post(payload, user_address)
        if not isinstance(data, dict) or data.get("status") != "order":
            return None
        wrapped = data.get("order", {})
        return wrapped if isinstance(wrapped, dict) else None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def get_historical_orders(self, user_address: str) -> list[dict[str, Any]]:
        """Return recent order history for reconnect gap recovery."""
        payload = {"type": "historicalOrders", "user": user_address}
        data = await self._post(payload, user_address)
        return data if isinstance(data, list) else []

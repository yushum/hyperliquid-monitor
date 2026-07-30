import logging
from typing import Any, Dict, List, Optional

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
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


class HyperliquidClient:
    """Hyperliquid Info API client with shared aiohttp session lifecycle."""

    def __init__(self, api_url: Optional[str] = None) -> None:
        self.api_url = api_url or settings.HL_API_URL
        self._session: Optional[aiohttp.ClientSession] = None

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

    async def _post(
        self, payload: Dict[str, Any], user_address: str = ""
    ) -> Any:
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
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        reraise=True,
    )
    async def get_clearinghouse_state(self, user_address: str) -> Dict[str, Any]:
        """Fetches the clearinghouse state (margin, positions) for an address."""
        payload = {
            "type": "clearinghouseState",
            "user": user_address,
        }
        return await self._post(payload, user_address)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        reraise=True,
    )
    async def get_open_orders(self, user_address: str) -> List[Dict[str, Any]]:
        """Fetches the current open orders for an address."""
        payload = {
            "type": "openOrders",
            "user": user_address,
        }
        data = await self._post(payload, user_address)
        return data if isinstance(data, list) else []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError)),
        reraise=True,
    )
    async def get_portfolio(self, user_address: str) -> List[Any]:
        """Fetches the historical portfolio stats (PnL, equity curve) for an address."""
        payload = {
            "type": "portfolio",
            "user": user_address,
        }
        data = await self._post(payload, user_address)
        return data if isinstance(data, list) else []

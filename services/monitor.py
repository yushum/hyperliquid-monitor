import asyncio
import hashlib
import logging
import random
import time
from collections import defaultdict
from typing import Any

import aiohttp

from core.config import settings
from infrastructure.db import (
    cleanup_event_history,
    get_all_address_notes,
    get_all_address_settings,
    get_due_notifications,
    get_last_fill_time,
    get_last_order_time,
    get_pending_notification_count,
    get_setting,
    get_unprocessed_event_keys,
    mark_notification_failed,
    mark_notification_sent,
    record_events,
    reschedule_notification,
    update_last_fill_time,
    update_last_order_time,
)
from services.notifier import BaseNotifier, PermanentNotificationError
from tg_bot.formatting import (
    escape_html,
    format_address_display,
    format_crypto_amount,
    format_pnl,
    format_price,
    format_timestamp,
    format_usd,
    unavailable,
)
from tg_bot.locales import (
    format_boolean,
    format_fill_badge,
    format_fill_direction,
    format_ledger_event,
    format_order_side,
    format_order_side_badge,
    format_order_status,
    format_order_status_badge,
    format_order_type,
    format_time_in_force,
    get_text,
)

logger = logging.getLogger(__name__)


class MonitorCapacityError(RuntimeError):
    """Raised when Hyperliquid's per-IP realtime user limit is reached."""


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert *value* to float, returning *default* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class BlockchainMonitor:
    """Listens to Hyperliquid WebSocket API for real-time fill events."""

    def __init__(
        self,
        notifier: BaseNotifier,
        ws_url: str | None = None,
        hl_client: Any | None = None,
    ) -> None:
        self.notifier = notifier
        self._hl_client = hl_client
        self._running = False
        self._flush_task: asyncio.Task | None = None
        self._order_flush_task: asyncio.Task | None = None
        self._outbox_task: asyncio.Task | None = None

        self.ws_url = ws_url or settings.HL_WS_URL
        self._session: aiohttp.ClientSession | None = None
        self._ws_tasks: dict[str, asyncio.Task] = {}
        self._websockets: dict[str, aiohttp.ClientWebSocketResponse] = {}
        self._monitored_addresses: dict[str, dict] = {}
        self._address_subscribed_at: dict[str, int] = {}
        self._address_notes: dict[str, str | None] = {}
        self._global_settings: dict[str, bool] = {}

        # Buffer for aggregating split fills within a short time window
        # key: (address, oid, coin) -> list[fills]
        self._fill_buffer: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
        self._buffer_lock = asyncio.Lock()
        self._pending_fill_keys: set[str] = set()

        # Buffer for aggregating order updates arriving within a short window
        self._order_buffer: list[dict[str, Any]] = []
        self._order_buffer_lock = asyncio.Lock()
        self._pending_order_keys: set[str] = set()

        # oid -> address best-effort mapping (orderUpdates payload has no user).
        # Populated from REST openOrders queries and from userFills.
        self._order_owner: dict[int, str] = {}
        self._order_details: dict[tuple[str, Any], dict[str, Any]] = {}

        self.min_notional_threshold = 0.0
        self._start_time = int(time.time() * 1000)

    @staticmethod
    def _fill_event_key(address: str, fill: dict[str, Any]) -> str:
        identity = fill.get("tid")
        if identity is None:
            identity = ":".join(
                str(fill.get(name, "")) for name in ("hash", "oid", "px", "sz", "side")
            )
        return (
            f"fill:{address.lower()}:{fill.get('time', 0)}:"
            f"{fill.get('coin', '')}:{identity}"
        )

    @staticmethod
    def _order_event_key(address: str, group: dict[str, Any]) -> str:
        order = group.get("order", {})
        return ":".join(
            str(value)
            for value in (
                "order",
                address.lower(),
                order.get("oid", ""),
                group.get("status", ""),
                group.get("statusTimestamp", order.get("timestamp", 0)),
                order.get("sz", ""),
            )
        )

    @staticmethod
    def _notification_key(prefix: str, event_keys: list[str]) -> str:
        digest = hashlib.sha256("\n".join(sorted(event_keys)).encode()).hexdigest()
        return f"{prefix}:{digest}"

    async def _record_notification(
        self,
        event_keys: list[tuple[str, int]],
        address: str,
        notify_type: str,
        message: str | None,
    ) -> bool:
        notification_key = (
            self._notification_key(notify_type, [key for key, _ in event_keys])
            if message is not None
            else None
        )
        return await record_events(
            event_keys,
            notification_key=notification_key,
            address=address,
            notify_type=notify_type,
            message=message,
        )

    async def _enqueue_system_notification(self, message: str) -> None:
        now_ms = int(time.time() * 1000)
        event_key = self._notification_key("system", [message])
        await self._record_notification([(event_key, now_ms)], "", "system", message)

    async def _deliver_due_notifications(self, limit: int = 50) -> int:
        delivered = 0
        for item in await get_due_notifications(limit):
            try:
                success = await self.notifier.notify(item["message"])
            except PermanentNotificationError as exc:
                error = f"{type(exc).__name__}: {exc}"
                await mark_notification_failed(item["id"], error)
                logger.error(
                    "Archived permanently undeliverable notification id=%s type=%s address=%s: %s",
                    item["id"],
                    item["notify_type"],
                    item["address"],
                    exc,
                )
                continue
            except Exception as exc:
                success = False
                error = f"{type(exc).__name__}: {exc}"
                logger.exception("Outbox delivery raised an exception.")
            else:
                error = "notifier returned delivery failure"

            if success:
                await mark_notification_sent(item["id"])
                delivered += 1
            else:
                attempts = int(item.get("attempts", 0)) + 1
                delay = min(2 ** min(attempts, 16), settings.OUTBOX_RETRY_MAX_SECONDS)
                await reschedule_notification(item["id"], error, delay)
                logger.warning(
                    "Notification delivery deferred id=%s attempt=%d delay=%.1fs type=%s address=%s",
                    item["id"],
                    attempts,
                    delay,
                    item["notify_type"],
                    item["address"],
                )
        return delivered

    async def _outbox_loop(self) -> None:
        try:
            await cleanup_event_history()
        except Exception:
            logger.exception("Failed to clean event history.")
        while self._running:
            try:
                await self._deliver_due_notifications()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox delivery iteration failed.")
            await asyncio.sleep(settings.OUTBOX_POLL_SECONDS)

    async def start(self) -> None:
        self._running = True

        threshold_str = await get_setting("min_notional_threshold", "0")
        try:
            self.min_notional_threshold = float(threshold_str)
        except ValueError:
            self.min_notional_threshold = 0.0

        self._global_settings = {
            "notify_fills": (await get_setting("global_notify_fills", "1")) == "1",
            "notify_orders": (await get_setting("global_notify_orders", "1")) == "1",
            "notify_events": (await get_setting("global_notify_events", "1")) == "1",
            "notify_fundings": (await get_setting("global_notify_fundings", "1"))
            == "1",
            "notify_ledger": (await get_setting("global_notify_ledger", "1")) == "1",
        }

        self._address_notes = await get_all_address_notes()
        self._monitored_addresses = await get_all_address_settings()
        active_addresses = list(self._monitored_addresses)[: settings.MAX_WS_USERS]
        for addr in active_addresses:
            self._address_subscribed_at[addr] = self._start_time

        # Best-effort: preload descriptive order fields. Fetch addresses in
        # parallel so one slow REST request does not delay every WS connection.
        if self._hl_client:
            await asyncio.gather(
                *(self._preload_open_orders(addr) for addr in active_addresses)
            )

        self._session = aiohttp.ClientSession()
        for address in active_addresses:
            self._start_address_connection(address)
        self._flush_task = asyncio.create_task(self._buffer_flush_loop())
        self._order_flush_task = asyncio.create_task(self._order_flush_loop())
        self._outbox_task = asyncio.create_task(self._outbox_loop())
        if len(self._monitored_addresses) > settings.MAX_WS_USERS:
            skipped = len(self._monitored_addresses) - settings.MAX_WS_USERS
            logger.exception(
                "Hyperliquid allows only %d realtime users per IP; %d addresses are inactive.",
                settings.MAX_WS_USERS,
                skipped,
            )
            await self._enqueue_system_notification(
                get_text(
                    settings.BOT_LANGUAGE,
                    "ws_capacity_startup",
                    active=settings.MAX_WS_USERS,
                    skipped=skipped,
                )
            )
        logger.info(
            "Starting Hyperliquid WS monitor with %d address connections...",
            len(active_addresses),
        )

    async def stop(self) -> None:
        """Gracefully shut down the monitor, awaiting task cancellation."""
        self._running = False

        # Stop producers before taking the final buffer snapshot.
        for ws in list(self._websockets.values()):
            if not ws.closed:
                await ws.close()

        ws_tasks = list(self._ws_tasks.values())
        for task in ws_tasks:
            task.cancel()
        for task in ws_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        background_tasks = [
            task
            for task in (self._flush_task, self._order_flush_task, self._outbox_task)
            if task is not None
        ]
        for task in background_tasks:
            task.cancel()
        for task in background_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self._flush_fill_buffer()
        await self._flush_order_buffer()
        try:
            await self._deliver_due_notifications()
            pending = await get_pending_notification_count()
            if pending:
                logger.warning(
                    "%d notifications remain safely queued for next startup.", pending
                )
        except Exception:
            logger.exception("Failed to drain notification outbox during shutdown.")

        if self._session and not self._session.closed:
            await self._session.close()

        logger.info("Hyperliquid WS monitor stopped.")

    def get_address_note(self, address: str) -> str | None:
        return self._address_notes.get(address.lower())

    def set_address_note(self, address: str, note: str | None) -> None:
        if note is None or str(note).strip() == "":
            self._address_notes.pop(address.lower(), None)
        else:
            self._address_notes[address.lower()] = str(note).strip()

    def format_address_display(self, address: str, lang_code: str = "zh") -> str:
        note = self.get_address_note(address)
        return format_address_display(address, note, lang_code)

    async def subscribe(
        self,
        address: str,
        addr_settings: dict | None = None,
        note: str | None = None,
    ) -> None:
        """Dynamically add an address to monitor via WS."""
        address = address.lower()
        if (
            address not in self._ws_tasks
            and len(self._ws_tasks) >= settings.MAX_WS_USERS
        ):
            raise MonitorCapacityError(
                f"Hyperliquid realtime user limit ({settings.MAX_WS_USERS}) reached"
            )
        if addr_settings is None:
            addr_settings = {}
        if note is not None:
            self.set_address_note(address, note)
        self._monitored_addresses[address] = addr_settings
        self._address_subscribed_at[address] = int(time.time() * 1000)
        if self._running:
            self._start_address_connection(address)

    async def unsubscribe(self, address: str) -> None:
        """Dynamically remove an address from WS monitor."""
        address = address.lower()
        self._monitored_addresses.pop(address, None)
        self._address_subscribed_at.pop(address, None)
        self.set_address_note(address, None)
        ws = self._websockets.pop(address, None)
        if ws and not ws.closed:
            await ws.close()
        task = self._ws_tasks.pop(address, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._activate_next_waiting_address()

    def available_realtime_slots(self) -> int:
        return max(settings.MAX_WS_USERS - len(self._ws_tasks), 0)

    def _start_address_connection(self, address: str) -> None:
        if address in self._ws_tasks:
            return
        task = asyncio.create_task(self._ws_loop(address))
        self._ws_tasks[address] = task
        task.add_done_callback(
            lambda _task, addr=address: self._ws_tasks.pop(addr, None)
        )

    def _activate_next_waiting_address(self) -> None:
        if not self._running or len(self._ws_tasks) >= settings.MAX_WS_USERS:
            return
        for address in self._monitored_addresses:
            if address not in self._ws_tasks:
                self._address_subscribed_at[address] = int(time.time() * 1000)
                self._start_address_connection(address)
                logger.info(
                    "Promoted waiting address to realtime monitoring: %s", address
                )
                return

    def set_global_setting(self, notify_type: str, enabled: bool) -> None:
        self._global_settings[f"notify_{notify_type}"] = enabled

    def set_address_setting(self, address: str, notify_type: str, state: str) -> None:
        if address in self._monitored_addresses:
            if state == "global":
                self._monitored_addresses[address].pop(f"notify_{notify_type}", None)
            else:
                self._monitored_addresses[address][f"notify_{notify_type}"] = state

    def is_notify_enabled(self, address: str, notify_type: str) -> bool:
        addr_settings = self._monitored_addresses.get(address, {})
        addr_pref = addr_settings.get(f"notify_{notify_type}")
        if addr_pref in ["1", "0"]:
            return addr_pref == "1"
        return self._global_settings.get(f"notify_{notify_type}", True)

    def register_order_owners(self, address: str, orders: list[dict[str, Any]]) -> None:
        """Map order ids returned by a REST query to their owning address."""
        address = address.lower()
        for o in orders:
            oid = o.get("oid")
            if oid:
                self._order_owner[oid] = address
                self._order_details[(address, oid)] = dict(o)
        if len(self._order_owner) > 10_000:
            self._order_owner = dict(list(self._order_owner.items())[-5_000:])
            self._order_details = {
                cache_key: details
                for cache_key, details in self._order_details.items()
                if cache_key[1] in self._order_owner
            }

    async def _preload_open_orders(self, address: str) -> None:
        try:
            orders = await self._hl_client.get_open_orders(address)
            self.register_order_owners(address, orders)
        except Exception:
            logger.exception("Failed to preload open orders for %s.", address)

    def _resolve_order_address(self, oid: Any) -> str:
        """Best effort attribution of an order update to a monitored address."""
        if oid and oid in self._order_owner:
            return self._order_owner[oid]
        if len(self._monitored_addresses) == 1:
            return next(iter(self._monitored_addresses))
        return ""

    async def _send_sub(
        self, ws: aiohttp.ClientWebSocketResponse, address: str, subscribe: bool
    ) -> None:
        if ws.closed:
            return
        method = "subscribe" if subscribe else "unsubscribe"
        channels = [
            "userFills",
            "orderUpdates",
            "userEvents",
            "userFundings",
            "userNonFundingLedgerUpdates",
        ]
        for ch in channels:
            msg = {
                "method": method,
                "subscription": {
                    "type": ch,
                    "user": address,
                },
            }
            await ws.send_json(msg)
        logger.info("Sent WS %s to 5 channels for %s", method, address)

    async def _ws_loop(self, address: str) -> None:
        reconnect_attempt = 0
        while self._running:
            # Guard against the session having been closed by stop().
            if self._session is None or self._session.closed:
                break
            ping_task: asyncio.Task | None = None
            connected_at: float | None = None
            try:
                # Do NOT use heartbeat= here — Hyperliquid's server does not
                # reply to WebSocket-level pings, so aiohttp would close the
                # connection after the heartbeat timeout.  We send our own
                # application-level {"method":"ping"} instead.
                async with self._session.ws_connect(self.ws_url) as ws:
                    self._websockets[address] = ws
                    connected_at = time.monotonic()
                    logger.info("Connected Hyperliquid WebSocket for %s.", address)
                    await self._send_sub(ws, address, subscribe=True)
                    await self._recover_missed_orders(address)

                    # Start application-level keepalive
                    ping_task = asyncio.create_task(self._ping_loop(ws))

                    async for msg in ws:
                        if not self._running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_message(msg.json(), address)
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("WebSocket loop failed for %s.", address)
            finally:
                self._websockets.pop(address, None)
                if ping_task is not None:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        pass

                # A server that accepts and immediately closes sockets should
                # continue through exponential backoff. Only a proven stable
                # connection clears the previous failure count.
                if connected_at is not None and time.monotonic() - connected_at >= 30:
                    reconnect_attempt = 0

            if self._running:
                reconnect_attempt += 1
                delay = min(5 * (2 ** (reconnect_attempt - 1)), 60)
                delay += random.uniform(0, min(delay * 0.2, 5))
                logger.warning(
                    "WebSocket for %s disconnected. Reconnecting in %.1fs...",
                    address,
                    delay,
                )
                await asyncio.sleep(delay)

    async def _recover_missed_orders(self, address: str) -> None:
        """Replay order states that may have occurred while WS was disconnected."""
        if not self._hl_client:
            return
        try:
            last_time = await get_last_order_time(address)
            history = await self._hl_client.get_historical_orders(address)
            if last_time == 0:
                # First observation establishes a baseline without alerting on up
                # to 2000 historical orders returned by the endpoint.
                await update_last_order_time(address, int(time.time() * 1000))
                return

            missed = [
                group
                for group in history
                if int(group.get("statusTimestamp", 0) or 0) > last_time
            ]
            if missed:
                missed.sort(key=lambda group: int(group.get("statusTimestamp", 0) or 0))
                logger.info(
                    "Recovering %d missed order updates for %s.", len(missed), address
                )
                await self._handle_order_updates(
                    {"data": missed}, address, allow_historical=True
                )
        except Exception:
            logger.exception("Failed to recover order history for %s.", address)

    async def _ping_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Send application-level pings to keep the Hyperliquid WS alive."""
        try:
            while not ws.closed:
                await asyncio.sleep(50)
                if not ws.closed:
                    await ws.send_json({"method": "ping"})
                    logger.debug("Sent WS application ping.")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("Ping loop ended.", exc_info=True)

    async def _handle_message(self, data: dict[str, Any], source_address: str) -> None:
        channel = data.get("channel")
        if channel == "userFills":
            await self._handle_user_fills(data)
        elif channel == "orderUpdates":
            await self._handle_order_updates(data, source_address)
        elif channel == "userEvents":
            await self._handle_user_events(data, source_address)
        elif channel == "userFundings":
            await self._handle_user_fundings(data, source_address)
        elif channel == "userNonFundingLedgerUpdates":
            await self._handle_ledger_updates(data, source_address)

    async def _handle_user_fills(self, data: dict[str, Any]) -> None:
        payload = data.get("data", {})
        user = payload.get("user")
        is_snapshot = payload.get("isSnapshot", False)
        fills = payload.get("fills", [])

        if not user or not fills:
            return

        try:
            last_time = await get_last_fill_time(user)
            keyed_fills = [(self._fill_event_key(user, fill), fill) for fill in fills]

            if is_snapshot and last_time == 0:
                latest_time = max((fill.get("time", 0) for fill in fills), default=0)
                await record_events(
                    [(key, int(fill.get("time", 0) or 0)) for key, fill in keyed_fills]
                )
                await update_last_fill_time(user, latest_time)
                return

            candidates = [
                (key, fill)
                for key, fill in keyed_fills
                if int(fill.get("time", 0) or 0) >= last_time
                and key not in self._pending_fill_keys
            ]
            unseen_keys = await get_unprocessed_event_keys(
                [key for key, _ in candidates]
            )
            new_fills = [(key, fill) for key, fill in candidates if key in unseen_keys]
            if not new_fills:
                return

            async with self._buffer_lock:
                for event_key, fill in new_fills:
                    oid = fill.get("oid", fill.get("tid", fill.get("time")))
                    coin = fill.get("coin") or ""
                    key = (user, oid, coin)
                    buffered_fill = dict(fill)
                    buffered_fill["_event_key"] = event_key
                    self._fill_buffer[key].append(buffered_fill)
                    self._pending_fill_keys.add(event_key)
                    # Fill payloads include the user, so learn who owns this order.
                    if oid:
                        self._order_owner[oid] = user

        except Exception:
            logger.exception("Error handling WS message.")

    async def _buffer_flush_loop(self) -> None:
        """Periodically flushes the fill buffer and sends aggregated alerts."""
        while self._running:
            try:
                await asyncio.sleep(settings.FILL_BUFFER_SECONDS)
                await self._flush_fill_buffer()

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in buffer flush loop.")

    async def _flush_fill_buffer(self) -> None:
        async with self._buffer_lock:
            if not self._fill_buffer:
                return
            current_buffer = self._fill_buffer
            self._fill_buffer = defaultdict(list)

        for buffer_key, fills in current_buffer.items():
            address, _oid, _coin = buffer_key
            try:
                unseen = await get_unprocessed_event_keys(
                    [str(fill["_event_key"]) for fill in fills]
                )
                pending_fills = [
                    fill for fill in fills if str(fill["_event_key"]) in unseen
                ]
                for fill in fills:
                    if str(fill["_event_key"]) not in unseen:
                        self._pending_fill_keys.discard(str(fill["_event_key"]))
                processed_fills = [
                    fill for fill in fills if str(fill["_event_key"]) not in unseen
                ]
                if processed_fills:
                    latest_processed = max(
                        int(fill.get("time", 0) or 0) for fill in processed_fills
                    )
                    if latest_processed:
                        await update_last_fill_time(address, latest_processed)
                if pending_fills:
                    await self._handle_aggregated_fills(pending_fills, address)
            except Exception:
                logger.exception("Failed to persist buffered fills; re-queueing.")
                async with self._buffer_lock:
                    self._fill_buffer[buffer_key][0:0] = fills

    async def _handle_aggregated_fills(
        self, fills: list[dict[str, Any]], address: str
    ) -> None:
        if not fills:
            return

        lang = settings.BOT_LANGUAGE
        coin = escape_html(fills[0].get("coin") or unavailable(lang))
        raw_dir = fills[0].get("dir")
        dir_badge = format_fill_badge(raw_dir, lang)
        trade_dir = escape_html(format_fill_direction(raw_dir, lang))

        total_size = sum(_safe_float(f.get("sz", 0)) for f in fills)
        total_fee = sum(_safe_float(f.get("fee", 0)) for f in fills)
        total_closed_pnl = sum(_safe_float(f.get("closedPnl", 0)) for f in fills)

        total_notional = sum(
            _safe_float(f.get("sz", 0)) * _safe_float(f.get("px", 0)) for f in fills
        )

        event_keys = [
            (str(fill["_event_key"]), int(fill.get("time", 0) or 0)) for fill in fills
        ]
        latest_time = max((event_time for _, event_time in event_keys), default=0)
        should_notify = not (
            self.min_notional_threshold > 0
            and total_notional < self.min_notional_threshold
        ) and self.is_notify_enabled(address, "fills")

        avg_price = (
            total_notional / total_size
            if total_size > 0
            else _safe_float(fills[0].get("px", 0))
        )

        last_fill = fills[-1]
        role = "吃单方 (Taker)" if lang == "zh" else "Taker"
        if "crossed" in last_fill:
            if lang == "zh":
                role = (
                    "吃单方 (Taker)" if last_fill.get("crossed") else "挂单方 (Maker)"
                )
            else:
                role = "Taker" if last_fill.get("crossed") else "Maker"
        oid = last_fill.get("oid", "")
        tx_hash = escape_html(last_fill.get("hash", ""))

        ts = last_fill.get("time", 0)
        time_str = format_timestamp(ts, lang)

        msg = None
        if should_notify:
            address_display = self.format_address_display(address, lang)
            pnl_line = ""
            if abs(total_closed_pnl) > 0.0001:
                pnl_formatted = format_pnl(total_closed_pnl, lang)
                if lang == "zh":
                    pnl_line = f"💰 <b>平仓盈亏:</b> {pnl_formatted}\n"
                else:
                    pnl_line = f"💰 <b>Realized PnL:</b> {pnl_formatted}\n"

            extra_parts = []
            if oid:
                if lang == "zh":
                    extra_parts.append(f"🔗 <b>订单 ID:</b> <code>#{oid}</code>")
                else:
                    extra_parts.append(f"🔗 <b>Order ID:</b> <code>#{oid}</code>")
            if tx_hash:
                if lang == "zh":
                    extra_parts.append(f"🔗 <b>交易哈希:</b> <code>{tx_hash}</code>")
                else:
                    extra_parts.append(f"🔗 <b>Tx Hash:</b> <code>{tx_hash}</code>")
            extra_line = "\n".join(extra_parts)

            msg = get_text(
                lang,
                "tx_alert",
                address=address,
                address_display=address_display,
                coin=coin,
                dir=trade_dir,
                dir_badge=dir_badge,
                price=format_price(avg_price),
                size=format_crypto_amount(total_size),
                notional=f"${total_notional:,.2f}",
                closed_pnl=f"{total_closed_pnl:.4f}",
                pnl_line=pnl_line,
                fee=f"${total_fee:,.4f}" if total_fee > 0 else "$0.00",
                role=role,
                oid=oid,
                hash=tx_hash,
                time=time_str,
                extra_line=extra_line,
            )
        logger.info(
            "Aggregated WS fill for %s: %s %s size=%.4f",
            address,
            coin,
            trade_dir,
            total_size,
        )
        await self._record_notification(event_keys, address, "fills", msg)
        if latest_time:
            await update_last_fill_time(address, latest_time)
        for event_key, _ in event_keys:
            self._pending_fill_keys.discard(event_key)

    async def _handle_order_updates(
        self,
        data: dict[str, Any],
        source_address: str | None = None,
        *,
        allow_historical: bool = False,
    ) -> None:
        """Handle orderUpdates channel events.

        Hyperliquid does not include the user in this payload. Each address has
        a dedicated connection, so ``source_address`` provides exact ownership.
        Durable event keys suppress reconnect snapshots and repeated updates.
        """
        payload = data.get("data", [])
        if not payload:
            return

        lang = settings.BOT_LANGUAGE
        for order_group in payload:
            order = order_group.get("order", {})
            if not order:
                continue

            oid = order.get("oid", "")
            address = source_address or self._resolve_order_address(oid)
            if not address:
                address = get_text(lang, "addr_unknown_multi")
            ts = order_group.get("statusTimestamp", order.get("timestamp", 0))
            # Discard the initial open-order snapshot before making REST calls
            # to enrich it; a large account should not cause a request burst.
            min_ts = self._address_subscribed_at.get(address, self._start_time)
            if not allow_historical and ts < min_ts:
                continue
            event_key = self._order_event_key(address, order_group)
            if event_key in self._pending_order_keys:
                continue
            if event_key not in await get_unprocessed_event_keys([event_key]):
                continue

            coin = escape_html(order.get("coin") or unavailable(lang))
            raw_side = order.get("side")

            raw_status = order_group.get("status", "unknown")
            status = escape_html(format_order_status(raw_status, lang))
            status_badge = format_order_status_badge(raw_status, lang)
            limit_px = _safe_float(order.get("limitPx", "0"))
            sz = _safe_float(order.get("sz", "0"))
            orig_sz = _safe_float(order.get("origSz", "0"))

            detail_key = (address.lower(), oid)
            details = self._order_details.get(detail_key, {}) if oid else {}
            if (
                oid
                and source_address
                and self._hl_client
                and not details
                and "orderType" not in order
            ):
                try:
                    status_record = await self._hl_client.get_order_status(
                        source_address, oid
                    )
                    if status_record:
                        full_order = status_record.get("order", {})
                        if isinstance(full_order, dict):
                            details = full_order
                            self._order_details[detail_key] = dict(full_order)
                except Exception:
                    logger.warning(
                        "Failed to enrich order %s for %s.",
                        oid,
                        source_address,
                        exc_info=True,
                    )
            if details:
                order = dict(order)
                for field in ("orderType", "tif", "reduceOnly", "origSz"):
                    if field not in order and field in details:
                        order[field] = details[field]
                is_reduce_only = bool(order.get("reduceOnly"))
                reduce_only = format_boolean(
                    order.get("reduceOnly"), lang, provided="reduceOnly" in order
                )
                orig_sz = _safe_float(order.get("origSz", orig_sz))
            else:
                is_reduce_only = bool(order.get("reduceOnly"))
                reduce_only = format_boolean(
                    order.get("reduceOnly"), lang, provided="reduceOnly" in order
                )
            dir_str = escape_html(
                format_order_side(raw_side, lang, reduce_only=is_reduce_only)
            )
            dir_badge = format_order_side_badge(
                raw_side, lang, reduce_only=is_reduce_only
            )
            order_type_raw = order.get("orderType")
            order_type = escape_html(format_order_type(order_type_raw, lang))
            time_in_force = escape_html(
                format_time_in_force(order.get("tif"), lang, order_type=order_type_raw)
            )

            time_str = format_timestamp(ts, lang)

            # Filled and canceled updates commonly have zero remaining size.
            # Use original size so the threshold does not hide final statuses.
            notional = max(sz, orig_sz) * limit_px
            if (
                self.min_notional_threshold > 0
                and notional < self.min_notional_threshold
            ):
                await record_events([(event_key, int(ts or 0))])
                await update_last_order_time(address, int(ts or 0))
                continue

            address_display = self.format_address_display(address, lang) if address and address != get_text(lang, "addr_unknown_multi") else (
                f"<i>{escape_html(address)}</i>" if address else "<i>未知</i>"
            )

            item = {
                "address": escape_html(address),
                "address_display": address_display,
                "address_raw": address,
                "coin": coin,
                "dir": dir_str,
                "dir_badge": dir_badge,
                "status": status,
                "status_badge": status_badge,
                "raw_status": raw_status,
                "limit_px": f"{limit_px:,.4f}",
                "price": format_price(limit_px),
                "sz": f"{sz:,.4f}",
                "orig_sz": f"{orig_sz:,.4f}",
                "notional": f"${notional:,.2f}",
                "oid": oid,
                "reduce_only": reduce_only,
                "order_type": order_type,
                "time_in_force": time_in_force,
                "time": time_str,
                "_event_key": event_key,
                "_event_time": int(ts or 0),
            }
            async with self._order_buffer_lock:
                self._order_buffer.append(item)
                self._pending_order_keys.add(event_key)

    async def _order_flush_loop(self) -> None:
        """Periodically flush buffered order updates as one notification."""
        while self._running:
            try:
                await asyncio.sleep(settings.ORDER_BUFFER_SECONDS)
                await self._flush_order_buffer()

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in order flush loop.")

    async def _flush_order_buffer(self) -> None:
        async with self._order_buffer_lock:
            if not self._order_buffer:
                return
            batched = self._order_buffer
            self._order_buffer = []

        try:
            unseen = await get_unprocessed_event_keys(
                [item["_event_key"] for item in batched]
            )
            pending = [item for item in batched if item["_event_key"] in unseen]
            for item in batched:
                if item["_event_key"] not in unseen:
                    self._pending_order_keys.discard(item["_event_key"])
            processed = [item for item in batched if item["_event_key"] not in unseen]
            if processed:
                await self._advance_order_cursors(processed)
            if pending:
                await self._send_order_batch(pending)
        except Exception:
            logger.exception("Failed to persist buffered orders; re-queueing.")
            async with self._order_buffer_lock:
                self._order_buffer[0:0] = batched

    async def _send_order_batch(self, items: list[dict[str, Any]]) -> None:
        """Send buffered order updates, merging bursts into one message."""
        enabled = [
            it for it in items if self.is_notify_enabled(it["address_raw"], "orders")
        ]
        disabled = [it for it in items if it not in enabled]
        if disabled:
            await record_events(
                [(it["_event_key"], it["_event_time"]) for it in disabled]
            )
            for item in disabled:
                self._pending_order_keys.discard(item["_event_key"])
            await self._advance_order_cursors(disabled)
        if not enabled:
            return

        groups: dict[Any, list[dict[str, Any]]] = {}
        for it in enabled:
            oid = it.get("oid")
            if oid:
                key = (it["address_raw"].lower(), oid)
            else:
                key = (it["address_raw"].lower(), f"no_oid_{it['_event_key']}")
            if key not in groups:
                groups[key] = []
            groups[key].append(it)

        to_notify: list[dict[str, Any]] = []
        superseded: list[dict[str, Any]] = []

        for key, group_items in groups.items():
            if len(group_items) > 1:
                superseded.extend(group_items[:-1])
            latest = group_items[-1]
            raw_status = str(latest.get("raw_status", "")).strip().lower()
            if raw_status == "filled" and self.is_notify_enabled(
                latest["address_raw"], "fills"
            ):
                superseded.append(latest)
            else:
                to_notify.append(latest)

        if superseded:
            await record_events(
                [(it["_event_key"], it["_event_time"]) for it in superseded]
            )
            for item in superseded:
                self._pending_order_keys.discard(item["_event_key"])
            await self._advance_order_cursors(superseded)

        if not to_notify:
            return

        lang = settings.BOT_LANGUAGE
        if len(to_notify) == 1:
            it = to_notify[0]
            msg = get_text(lang, "order_update_alert", **it)
            await self._record_notification(
                [(it["_event_key"], it["_event_time"])],
                it["address_raw"],
                "orders",
                msg,
            )
            self._pending_order_keys.discard(it["_event_key"])
            await self._advance_order_cursors([it])
            return

        # Batch message; chunk at ~3500 chars to stay under Telegram limits.
        chunks: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_len = 0
        for it in to_notify:
            line = get_text(lang, "order_update_item", **it) + "\n\n"
            if current and current_len + len(line) > 3500:
                chunks.append(current)
                current = []
                current_len = 0
            current.append(it)
            current_len += len(line)
        if current:
            chunks.append(current)

        for idx, chunk in enumerate(chunks):
            body = "".join(
                get_text(lang, "order_update_item", **item) + "\n\n" for item in chunk
            )
            if idx == 0:
                msg = get_text(
                    lang, "order_updates_batch_alert", count=len(to_notify), items=body
                )
            else:
                msg = body.rstrip("\n")
            event_keys = [(item["_event_key"], item["_event_time"]) for item in chunk]
            await self._record_notification(
                event_keys, chunk[0]["address_raw"], "orders", msg
            )
            for event_key, _ in event_keys:
                self._pending_order_keys.discard(event_key)
            await self._advance_order_cursors(chunk)

    async def _advance_order_cursors(self, items: list[dict[str, Any]]) -> None:
        latest_by_address: dict[str, int] = {}
        for item in items:
            address = item["address_raw"]
            latest_by_address[address] = max(
                latest_by_address.get(address, 0), int(item["_event_time"] or 0)
            )
        for address, latest_time in latest_by_address.items():
            if latest_time:
                await update_last_order_time(address, latest_time)

    async def _handle_user_events(
        self, data: dict[str, Any], source_address: str | None = None
    ) -> None:
        payload = data.get("data", {})
        if not payload or payload.get("isSnapshot"):
            return

        lang = settings.BOT_LANGUAGE
        event_type = "未知事件" if lang == "zh" else "Unknown event"
        address = ""
        asset = "账户" if lang == "zh" else "Account"
        extra = ""
        notional_str = "$0.00"
        account_val_str = "$0.00"
        liquidator_display = "未知" if lang == "zh" else "Unknown"
        ts = int(time.time() * 1000)

        if "liquidation" in payload:
            liq = payload["liquidation"]
            event_type = "账户强平" if lang == "zh" else "Liquidation"
            address = str(liq.get("liquidated_user") or source_address or "")
            liquidator = str(liq.get("liquidator") or "")
            notional = abs(_safe_float(liq.get("liquidated_ntl_pos", 0)))
            account_value = _safe_float(liq.get("liquidated_account_value", 0))

            event_key = (
                f"liquidation:{(source_address or address).lower()}:"
                f"{liq.get('lid', '')}:{liq.get('liquidated_ntl_pos', '')}"
            )
            if (
                self.min_notional_threshold > 0
                and notional < self.min_notional_threshold
            ):
                await record_events([(event_key, ts)])
                return

            notional_str = f"${notional:,.2f}"
            account_val_str = f"${account_value:,.2f}"
            liquidator_display = (
                f"<code>{escape_html(liquidator)}</code>"
                if liquidator
                else ("未知" if lang == "zh" else "Unknown")
            )

            if lang == "zh":
                extra = (
                    f"被强平名义仓位: ${notional:,.2f}\n"
                    f"强平时账户价值: ${account_value:,.2f}\n"
                    f"清算方: <code>{escape_html(liquidator)}</code>\n"
                )
            else:
                extra = (
                    f"Liquidated Notional: ${notional:,.2f}\n"
                    f"Account Value: ${account_value:,.2f}\n"
                    f"Liquidator: <code>{escape_html(liquidator)}</code>\n"
                )

        time_str = format_timestamp(ts, lang)

        if address:
            address_display = self.format_address_display(address, lang)
            msg = get_text(
                lang,
                "event_alert",
                address=escape_html(address),
                address_display=address_display,
                event_type=event_type,
                asset=asset,
                extra=extra,
                notional=notional_str,
                account_value=account_val_str,
                liquidator=liquidator_display,
                time=time_str,
            )
            settings_address = source_address or address
            await self._record_notification(
                [(event_key, ts)],
                settings_address,
                "events",
                msg if self.is_notify_enabled(settings_address, "events") else None,
            )

    async def _handle_user_fundings(
        self, data: dict[str, Any], source_address: str | None = None
    ) -> None:
        payload = data.get("data", {})
        if not payload or payload.get("isSnapshot"):
            return

        lang = settings.BOT_LANGUAGE
        user = str(payload.get("user") or source_address or "")
        fundings = payload.get("fundings", [])

        for f in fundings:
            coin = escape_html(f.get("coin") or unavailable(lang))
            usdc = _safe_float(f.get("usdc", "0"))
            szi = _safe_float(f.get("szi", "0"))
            funding_rate = _safe_float(f.get("fundingRate", "0"))
            ts = f.get("time", 0)
            event_key = (
                f"funding:{user.lower()}:{ts}:{f.get('coin', '')}:"
                f"{f.get('usdc', '')}:{f.get('fundingRate', '')}"
            )

            if ts < self._start_time:
                continue

            if (
                self.min_notional_threshold > 0
                and abs(usdc) < self.min_notional_threshold
            ):
                await record_events([(event_key, int(ts or 0))])
                continue

            time_str = format_timestamp(ts, lang)
            address_display = self.format_address_display(user, lang)

            if usdc > 0.000001:
                payment_display = f"🟢 <code>+${usdc:,.4f}</code>"
            elif usdc < -0.000001:
                payment_display = f"🔴 <code>-${abs(usdc):,.4f}</code>"
            else:
                payment_display = "<code>$0.0000</code>"

            szi_display = f"{format_crypto_amount(szi)} {coin}"

            msg = get_text(
                lang,
                "funding_alert",
                address=escape_html(user),
                address_display=address_display,
                coin=coin,
                payment=f"{usdc:,.4f}",
                payment_display=payment_display,
                szi=f"{szi:,.4f}",
                szi_display=szi_display,
                funding_rate=f"{funding_rate:.6%}",
                time=time_str,
            )
            await self._record_notification(
                [(event_key, int(ts or 0))],
                user,
                "fundings",
                msg if self.is_notify_enabled(user, "fundings") else None,
            )

    async def _handle_ledger_updates(
        self, data: dict[str, Any], source_address: str | None = None
    ) -> None:
        payload = data.get("data", {})
        if not payload or payload.get("isSnapshot"):
            return

        lang = settings.BOT_LANGUAGE
        user = str(payload.get("user") or source_address or "")
        updates = payload.get("updates", [])

        for u in updates:
            delta = u.get("delta", {})
            event_type = escape_html(
                format_ledger_event(delta.get("type"), lang)
            )
            usdc = _safe_float(delta.get("usdc", "0"))
            ts = u.get("time", 0)
            tx_hash = escape_html(u.get("hash", ""))
            event_key = (
                f"ledger:{user.lower()}:{ts}:{u.get('hash', '')}:"
                f"{delta.get('type', '')}:{delta.get('usdc', '')}"
            )

            if ts < self._start_time:
                continue

            if (
                self.min_notional_threshold > 0
                and abs(usdc) < self.min_notional_threshold
            ):
                await record_events([(event_key, int(ts or 0))])
                continue

            time_str = format_timestamp(ts, lang)
            address_display = self.format_address_display(user, lang)

            if usdc > 0.000001:
                amount_display = f"🟢 <code>+${usdc:,.4f}</code>"
            elif usdc < -0.000001:
                amount_display = f"🔴 <code>-${abs(usdc):,.4f}</code>"
            else:
                amount_display = "<code>$0.0000</code>"

            hash_line = ""
            if tx_hash:
                if lang == "zh":
                    hash_line = f"🔗 <b>交易哈希:</b> <code>{tx_hash}</code>\n"
                else:
                    hash_line = f"🔗 <b>Tx Hash:</b> <code>{tx_hash}</code>\n"

            msg = get_text(
                lang,
                "ledger_update_alert",
                address=escape_html(user),
                address_display=address_display,
                event_type=event_type,
                amount=f"{usdc:,.4f}",
                amount_display=amount_display,
                hash=tx_hash,
                hash_line=hash_line,
                time=time_str,
            )
            await self._record_notification(
                [(event_key, int(ts or 0))],
                user,
                "ledger",
                msg if self.is_notify_enabled(user, "ledger") else None,
            )

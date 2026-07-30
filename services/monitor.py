import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

import time
import aiohttp

from core.config import settings
from infrastructure.db import get_all_address_settings, get_last_fill_time, update_last_fill_time, get_setting
from services.notifier import BaseNotifier
from tg_bot.locales import get_text

logger = logging.getLogger(__name__)

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
        ws_url: Optional[str] = None,
    ) -> None:
        self.notifier = notifier
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._flush_task: Optional[asyncio.Task] = None

        self.ws_url = ws_url or settings.HL_WS_URL
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._monitored_addresses: Dict[str, dict] = {}
        self._global_settings: Dict[str, bool] = {}

        # Buffer for aggregating split fills within a short time window
        # key: (address, oid, coin) -> List[fills]
        self._fill_buffer: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        self._buffer_lock = asyncio.Lock()
        
        self.min_notional_threshold = 0.0
        self._start_time = int(time.time() * 1000)

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
            "notify_fundings": (await get_setting("global_notify_fundings", "1")) == "1",
            "notify_ledger": (await get_setting("global_notify_ledger", "1")) == "1",
        }
            
        self._monitored_addresses = await get_all_address_settings()

        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._ws_loop())
        self._flush_task = asyncio.create_task(self._buffer_flush_loop())
        logger.info("Starting Hyperliquid WS monitor...")

    async def stop(self) -> None:
        """Gracefully shut down the monitor, awaiting task cancellation."""
        self._running = False

        # Close the WebSocket first so the reader loop exits cleanly.
        if self._ws and not self._ws.closed:
            await self._ws.close()

        # Cancel tasks and wait for them to actually finish.
        for task in (self._task, self._flush_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._session and not self._session.closed:
            await self._session.close()

        logger.info("Hyperliquid WS monitor stopped.")

    async def subscribe(self, address: str, addr_settings: Optional[dict] = None) -> None:
        """Dynamically add an address to monitor via WS."""
        if addr_settings is None:
            addr_settings = {}
        self._monitored_addresses[address] = addr_settings
        if self._ws and not self._ws.closed:
            await self._send_sub(address, subscribe=True)

    async def unsubscribe(self, address: str) -> None:
        """Dynamically remove an address from WS monitor."""
        self._monitored_addresses.pop(address, None)
        if self._ws and not self._ws.closed:
            await self._send_sub(address, subscribe=False)
            
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

    async def _send_sub(self, address: str, subscribe: bool) -> None:
        if not self._ws or self._ws.closed:
            return
        method = "subscribe" if subscribe else "unsubscribe"
        channels = [
            "userFills", 
            "orderUpdates", 
            "userEvents", 
            "userFundings", 
            "userNonFundingLedgerUpdates"
        ]
        for ch in channels:
            msg = {
                "method": method,
                "subscription": {
                    "type": ch,
                    "user": address,
                },
            }
            await self._ws.send_json(msg)
        logger.info("Sent WS %s to 5 channels for %s", method, address)

    async def _ws_loop(self) -> None:
        while self._running:
            # Guard against the session having been closed by stop().
            if self._session is None or self._session.closed:
                break
            ping_task: Optional[asyncio.Task] = None
            try:
                # Do NOT use heartbeat= here — Hyperliquid's server does not
                # reply to WebSocket-level pings, so aiohttp would close the
                # connection after the heartbeat timeout.  We send our own
                # application-level {"method":"ping"} instead.
                async with self._session.ws_connect(self.ws_url) as ws:
                    self._ws = ws
                    logger.info("Connected to Hyperliquid WebSocket.")

                    # Resubscribe all addresses on reconnect
                    for addr in list(self._monitored_addresses.keys()):
                        await self._send_sub(addr, subscribe=True)

                    # Start application-level keepalive
                    ping_task = asyncio.create_task(self._ping_loop(ws))

                    async for msg in ws:
                        if not self._running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_message(msg.json())
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("WebSocket error: %s", e)
            finally:
                if ping_task is not None:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        pass

            if self._running:
                logger.warning("WebSocket disconnected. Reconnecting in 5s...")
                await asyncio.sleep(5)

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

    async def _handle_message(self, data: Dict[str, Any]) -> None:
        channel = data.get("channel")
        if channel == "userFills":
            await self._handle_user_fills(data)
        elif channel == "orderUpdates":
            await self._handle_order_updates(data)
        elif channel == "userEvents":
            await self._handle_user_events(data)
        elif channel == "userFundings":
            await self._handle_user_fundings(data)
        elif channel == "userNonFundingLedgerUpdates":
            await self._handle_ledger_updates(data)

    async def _handle_user_fills(self, data: Dict[str, Any]) -> None:
        payload = data.get("data", {})
        user = payload.get("user")
        is_snapshot = payload.get("isSnapshot", False)
        fills = payload.get("fills", [])

        if not user or not fills:
            return

        try:
            last_time = await get_last_fill_time(user)

            if is_snapshot and last_time == 0:
                latest_time = max(
                    (fill.get("time", 0) for fill in fills), default=0
                )
                await update_last_fill_time(user, latest_time)
                return

            new_fills = [f for f in fills if f.get("time", 0) > last_time]
            if not new_fills:
                return

            async with self._buffer_lock:
                for fill in new_fills:
                    oid = fill.get("oid", fill.get("tid", fill.get("time")))
                    coin = fill.get("coin", "Unknown")
                    key = (user, oid, coin)
                    self._fill_buffer[key].append(fill)

            latest_time = max(
                (f.get("time", 0) for f in new_fills), default=last_time
            )
            if latest_time > last_time:
                await update_last_fill_time(user, latest_time)

        except Exception:
            logger.error("Error handling WS message.", exc_info=True)

    async def _buffer_flush_loop(self) -> None:
        """Periodically flushes the fill buffer and sends aggregated alerts."""
        while self._running:
            try:
                await asyncio.sleep(settings.FILL_BUFFER_SECONDS)

                # Swap buffer under lock so no fills are lost.
                async with self._buffer_lock:
                    if not self._fill_buffer:
                        continue
                    current_buffer = self._fill_buffer
                    self._fill_buffer = defaultdict(list)

                for (address, _oid, _coin), fills in current_buffer.items():
                    await self._handle_aggregated_fills(fills, address)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("Error in buffer flush loop.", exc_info=True)

    async def _handle_aggregated_fills(
        self, fills: List[Dict[str, Any]], address: str
    ) -> None:
        if not fills:
            return

        coin = fills[0].get("coin", "Unknown")
        trade_dir = fills[0].get("dir", "Unknown")

        total_size = sum(_safe_float(f.get("sz", 0)) for f in fills)
        total_fee = sum(_safe_float(f.get("fee", 0)) for f in fills)
        total_closed_pnl = sum(_safe_float(f.get("closedPnl", 0)) for f in fills)

        total_notional = sum(
            _safe_float(f.get("sz", 0)) * _safe_float(f.get("px", 0))
            for f in fills
        )
        
        if self.min_notional_threshold > 0 and total_notional < self.min_notional_threshold:
            return
            
        avg_price = (
            total_notional / total_size
            if total_size > 0
            else _safe_float(fills[0].get("px", 0))
        )
        
        last_fill = fills[-1]
        role = "Taker"
        if "crossed" in last_fill:
            role = "Taker" if last_fill.get("crossed") else "Maker"
        oid = last_fill.get("oid", "")
        tx_hash = last_fill.get("hash", "")
        
        ts = last_fill.get("time", 0)
        from datetime import datetime
        time_str = datetime.fromtimestamp(ts / 1000.0).strftime('%Y-%m-%d %H:%M:%S') if ts else "Unknown"

        msg = get_text(
            settings.BOT_LANGUAGE,
            "tx_alert",
            address=address,
            coin=coin,
            dir=trade_dir,
            price=f"{avg_price:.4f}",
            size=f"{total_size:.4f}",
            closed_pnl=f"{total_closed_pnl:.4f}",
            fee=f"{total_fee:.4f}",
            role=role,
            oid=oid,
            hash=tx_hash,
            time=time_str
        )
        logger.info(
            "Aggregated WS fill for %s: %s %s size=%.4f",
            address,
            coin,
            trade_dir,
            total_size,
        )
        if self.is_notify_enabled(address, "fills"):
            await self.notifier.notify(msg)


    async def _handle_order_updates(self, data: Dict[str, Any]) -> None:
        payload = data.get("data", [])
        if not payload:
            return
        
        from datetime import datetime
        for order_group in payload:
            order = order_group.get("order", {})
            if not order:
                continue
            
            coin = order.get("coin", "Unknown")
            side = order.get("side", "")
            if side == "B":
                dir_str = get_text(settings.BOT_LANGUAGE, "pos_long") if settings.BOT_LANGUAGE == "zh" else "Buy"
            else:
                dir_str = get_text(settings.BOT_LANGUAGE, "pos_short") if settings.BOT_LANGUAGE == "zh" else "Sell"
                
            status = order_group.get("status", "Unknown")
            limit_px = _safe_float(order.get("limitPx", "0"))
            sz = _safe_float(order.get("sz", "0"))
            orig_sz = _safe_float(order.get("origSz", "0"))
            oid = order.get("oid", "")
            reduce_only = "Yes" if order.get("reduceOnly") else "No"
            post_only = "Yes" if order.get("postOnly") else "No"
            tif = order.get("tif", "Unknown")
            
            ts = order_group.get("statusTimestamp", order.get("timestamp", 0))
            if ts < self._start_time:
                continue
                
            time_str = datetime.fromtimestamp(ts / 1000.0).strftime('%Y-%m-%d %H:%M:%S') if ts else "Unknown"
            
            notional = sz * limit_px
            if self.min_notional_threshold > 0 and notional < self.min_notional_threshold:
                continue
                
            address = "Unknown"
            if len(self._monitored_addresses) == 1:
                address = list(self._monitored_addresses.keys())[0]
                
            msg = get_text(
                settings.BOT_LANGUAGE,
                "order_update_alert",
                address=address,
                coin=coin,
                dir=dir_str,
                status=status,
                limit_px=f"{limit_px:,.4f}",
                sz=f"{sz:,.4f}",
                orig_sz=f"{orig_sz:,.4f}",
                oid=oid,
                reduce_only=reduce_only,
                post_only=post_only,
                tif=tif,
                time=time_str
            )
            if self.is_notify_enabled(address, "orders"):
                await self.notifier.notify(msg)

    async def _handle_user_events(self, data: Dict[str, Any]) -> None:
        payload = data.get("data", {})
        if not payload or payload.get("isSnapshot"):
            return
            
        address = payload.get("user", "Unknown")
        from datetime import datetime
        
        event_type = "Unknown"
        asset = "USDC"
        extra = ""
        ts = 0
        
        if "liquidation" in payload:
            liq = payload["liquidation"]
            event_type = "Liquidation"
            asset = liq.get("coin", "Unknown")
            liq_px = _safe_float(liq.get("liqPx", 0))
            sz = _safe_float(liq.get("sz", 0))
            ts = liq.get("time", 0)
            
            if ts < self._start_time:
                return
            
            notional = sz * liq_px
            if self.min_notional_threshold > 0 and notional < self.min_notional_threshold:
                return
                
            if settings.BOT_LANGUAGE == "zh":
                extra = f"强平价格: {liq_px:,.4f}\n被强平数量: {sz:,.4f}\n"
            else:
                extra = f"Liq Px: {liq_px:,.4f}\nLiquidated Sz: {sz:,.4f}\n"
        
        time_str = datetime.fromtimestamp(ts / 1000.0).strftime('%Y-%m-%d %H:%M:%S') if ts else "Unknown"
        
        if event_type != "Unknown":
            msg = get_text(
                settings.BOT_LANGUAGE,
                "event_alert",
                address=address,
                event_type=event_type,
                asset=asset,
                extra=extra,
                time=time_str
            )
            if self.is_notify_enabled(address, "events"):
                await self.notifier.notify(msg)

    async def _handle_user_fundings(self, data: Dict[str, Any]) -> None:
        payload = data.get("data", {})
        if not payload or payload.get("isSnapshot"):
            return
            
        user = payload.get("user", "Unknown")
        fundings = payload.get("fundings", [])
        
        from datetime import datetime
        for f in fundings:
            coin = f.get("coin", "Unknown")
            usdc = _safe_float(f.get("usdc", "0"))
            szi = _safe_float(f.get("szi", "0"))
            funding_rate = _safe_float(f.get("fundingRate", "0"))
            ts = f.get("time", 0)
            
            if ts < self._start_time:
                continue
            
            if self.min_notional_threshold > 0 and abs(usdc) < self.min_notional_threshold:
                continue
            
            time_str = datetime.fromtimestamp(ts / 1000.0).strftime('%Y-%m-%d %H:%M:%S') if ts else "Unknown"
            
            msg = get_text(
                settings.BOT_LANGUAGE,
                "funding_alert",
                address=user,
                coin=coin,
                payment=f"{usdc:,.4f}",
                szi=f"{szi:,.4f}",
                funding_rate=f"{funding_rate:.6%}",
                time=time_str
            )
            if self.is_notify_enabled(user, "fundings"):
                await self.notifier.notify(msg)

    async def _handle_ledger_updates(self, data: Dict[str, Any]) -> None:
        payload = data.get("data", {})
        if not payload or payload.get("isSnapshot"):
            return
            
        user = payload.get("user", "Unknown")
        updates = payload.get("updates", [])
        
        from datetime import datetime
        for u in updates:
            delta = u.get("delta", {})
            event_type = delta.get("type", "Unknown")
            usdc = _safe_float(delta.get("usdc", "0"))
            ts = u.get("time", 0)
            tx_hash = u.get("hash", "")
            
            if ts < self._start_time:
                continue
            
            if self.min_notional_threshold > 0 and abs(usdc) < self.min_notional_threshold:
                continue
            
            time_str = datetime.fromtimestamp(ts / 1000.0).strftime('%Y-%m-%d %H:%M:%S') if ts else "Unknown"
            
            msg = get_text(
                settings.BOT_LANGUAGE,
                "ledger_update_alert",
                address=user,
                event_type=event_type,
                amount=f"{usdc:,.4f}",
                hash=tx_hash,
                time=time_str
            )
            if self.is_notify_enabled(user, "ledger"):
                await self.notifier.notify(msg)

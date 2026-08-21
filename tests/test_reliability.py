import os
import time
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TG_BOT_TOKEN", "test-token")
os.environ.setdefault("TG_ADMIN_CHAT_ID", "1")
os.environ.setdefault("BOT_LANGUAGE", "zh")

from core.config import settings
from services.monitor import BlockchainMonitor, MonitorCapacityError
from services.notifier import BaseNotifier, PermanentNotificationError


class StubNotifier(BaseNotifier):
    def __init__(self, succeeds: bool = True) -> None:
        self.succeeds = succeeds
        self.messages: list[str] = []

    async def notify(self, message: str) -> bool:
        self.messages.append(message)
        return self.succeeds


class PermanentlyFailingNotifier(BaseNotifier):
    async def notify(self, message: str) -> bool:
        raise PermanentNotificationError("chat is unavailable")


class EnrichingClient:
    async def get_order_status(self, address, oid):
        return {
            "status": "open",
            "statusTimestamp": 1_700_000_000_000,
            "order": {
                "oid": oid,
                "orderType": "Stop Market",
                "tif": "Alo",
                "reduceOnly": True,
                "origSz": "2",
            },
        }


class HistoricalClient:
    def __init__(self, orders):
        self.orders = orders

    async def get_historical_orders(self, address):
        return self.orders

    async def get_order_status(self, address, oid):
        return None


class AccountHistoryClient:
    def __init__(self, fundings=None, ledger=None):
        self.fundings = fundings or []
        self.ledger = ledger or []
        self.calls = []

    async def get_user_funding(self, address, start_time):
        self.calls.append(("funding", address, start_time))
        return self.fundings

    async def get_user_ledger_updates(self, address, start_time):
        self.calls.append(("ledger", address, start_time))
        return self.ledger


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_fill_buffer_waits_for_quiet_period_but_honors_max_wait(self) -> None:
        address = "0x" + "1" * 40
        key = (address, 7, "BTC")
        monitor = BlockchainMonitor(StubNotifier())
        monitor._fill_buffer[key].append(
            {"_event_key": "fill:1", "time": 100, "coin": "BTC"}
        )
        now = time.monotonic()
        monitor._fill_buffer_started_at[key] = now
        monitor._fill_buffer_updated_at[key] = now
        monitor._handle_aggregated_fills = AsyncMock()

        await monitor._flush_fill_buffer()
        monitor._handle_aggregated_fills.assert_not_awaited()
        self.assertIn(key, monitor._fill_buffer)

        monitor._fill_buffer_started_at[key] = (
            time.monotonic() - settings.FILL_MAX_WAIT_SECONDS - 1
        )
        with patch(
            "services.monitor.get_unprocessed_event_keys",
            AsyncMock(return_value={"fill:1"}),
        ):
            await monitor._flush_fill_buffer()
        monitor._handle_aggregated_fills.assert_awaited_once()
        self.assertNotIn(key, monitor._fill_buffer)

    async def test_order_buffer_waits_for_quiet_period_but_honors_max_wait(
        self,
    ) -> None:
        monitor = BlockchainMonitor(StubNotifier())
        item = {
            "_event_key": "order:1",
            "_event_time": 100,
            "address_raw": "0x" + "1" * 40,
        }
        monitor._order_buffer.append(item)
        now = time.monotonic()
        monitor._order_buffer_started_at = now
        monitor._order_buffer_updated_at = now
        monitor._send_order_batch = AsyncMock()

        await monitor._flush_order_buffer()
        monitor._send_order_batch.assert_not_awaited()
        self.assertEqual(monitor._order_buffer, [item])

        monitor._order_buffer_started_at = (
            time.monotonic() - settings.ORDER_MAX_WAIT_SECONDS - 1
        )
        with patch(
            "services.monitor.get_unprocessed_event_keys",
            AsyncMock(return_value={"order:1"}),
        ):
            await monitor._flush_order_buffer()

        monitor._send_order_batch.assert_awaited_once_with([item])
        self.assertEqual(monitor._order_buffer, [])

    async def test_account_event_recovery_uses_persisted_cursors(self) -> None:
        address = "0x" + "9" * 40
        funding = {"time": 201, "coin": "BTC", "usdc": "1"}
        ledger = {"time": 301, "hash": "0x1", "delta": {"usdc": "2"}}
        client = AccountHistoryClient([funding], [ledger])
        monitor = BlockchainMonitor(StubNotifier(), hl_client=client)
        monitor._address_subscribed_at[address] = 500
        monitor._handle_user_fundings = AsyncMock()
        monitor._handle_ledger_updates = AsyncMock()

        with (
            patch(
                "services.monitor.get_last_funding_time",
                AsyncMock(return_value=200),
            ),
            patch(
                "services.monitor.get_last_ledger_time",
                AsyncMock(return_value=300),
            ),
        ):
            await monitor._recover_missed_account_events(address)

        self.assertEqual(
            client.calls,
            [("funding", address, 200), ("ledger", address, 300)],
        )
        self.assertTrue(
            monitor._handle_user_fundings.await_args.kwargs["allow_historical"]
        )
        self.assertTrue(
            monitor._handle_ledger_updates.await_args.kwargs["allow_historical"]
        )

    async def test_source_connection_gives_exact_order_owner_and_enrichment(
        self,
    ) -> None:
        source = "0x" + "2" * 40
        other = "0x" + "1" * 40
        monitor = BlockchainMonitor(StubNotifier(), hl_client=EnrichingClient())
        monitor._monitored_addresses = {other: {}, source: {}}
        monitor._address_subscribed_at = {source: 0}
        group = {
            "status": "open",
            "statusTimestamp": 1_700_000_000_000,
            "order": {
                "coin": "BTC",
                "side": "B",
                "limitPx": "2000",
                "sz": "2",
                "origSz": "2",
                "oid": 99,
                "timestamp": 1_700_000_000_000,
            },
        }
        event_key = monitor._order_event_key(source, group)
        with patch(
            "services.monitor.get_unprocessed_event_keys",
            AsyncMock(return_value={event_key}),
        ):
            await monitor._handle_order_updates({"data": [group]}, source)

        item = monitor._order_buffer[0]
        self.assertEqual(item["address_raw"], source)
        self.assertEqual(item["order_type"], "止损市价单")
        self.assertIn("仅挂单", item["time_in_force"])
        self.assertEqual(item["reduce_only"], "是")

    async def test_order_enrichment_runs_when_reduce_only_is_missing(self) -> None:
        address = "0x" + "3" * 40
        monitor = BlockchainMonitor(StubNotifier(), hl_client=EnrichingClient())
        monitor._monitored_addresses = {address: {}}
        monitor._address_subscribed_at = {address: 0}
        group = {
            "status": "open",
            "statusTimestamp": 1_700_000_000_000,
            "order": {
                "coin": "BTC",
                "side": "B",
                "limitPx": "2000",
                "sz": "2",
                "origSz": "2",
                "oid": 100,
                "orderType": "Limit",
            },
        }
        event_key = monitor._order_event_key(address, group)
        with patch(
            "services.monitor.get_unprocessed_event_keys",
            AsyncMock(return_value={event_key}),
        ):
            await monitor._handle_order_updates({"data": [group]}, address)

        self.assertEqual(monitor._order_buffer[0]["dir"], "平空")
        self.assertEqual(monitor._order_buffer[0]["reduce_only"], "是")

    async def test_cached_order_details_are_address_scoped_and_non_destructive(
        self,
    ) -> None:
        first = "0x" + "a" * 40
        second = "0x" + "b" * 40
        monitor = BlockchainMonitor(StubNotifier())
        monitor._address_subscribed_at = {first: 0, second: 0}
        monitor.register_order_owners(
            first,
            [{"oid": 9, "orderType": "Stop Market", "sz": "99"}],
        )
        monitor.register_order_owners(
            second,
            [{"oid": 9, "orderType": "Limit", "sz": "88"}],
        )
        group = {
            "status": "filled",
            "statusTimestamp": 200,
            "order": {
                "oid": 9,
                "coin": "BTC",
                "limitPx": "10",
                "sz": "0",
                "origSz": "2",
            },
        }
        event_key = monitor._order_event_key(first, group)
        with patch(
            "services.monitor.get_unprocessed_event_keys",
            AsyncMock(return_value={event_key}),
        ):
            await monitor._handle_order_updates({"data": [group]}, first)

        item = monitor._order_buffer[0]
        self.assertEqual(item["order_type"], "止损市价单")
        self.assertEqual(item["sz"], "0.0000")

    async def test_fill_at_same_millisecond_is_not_discarded(self) -> None:
        address = "0x" + "4" * 40
        monitor = BlockchainMonitor(StubNotifier())
        fill = {
            "coin": "ETH",
            "time": 100,
            "tid": 123,
            "oid": 456,
            "px": "10",
            "sz": "1",
        }
        event_key = monitor._fill_event_key(address, fill)
        with (
            patch("services.monitor.get_last_fill_time", AsyncMock(return_value=100)),
            patch(
                "services.monitor.get_unprocessed_event_keys",
                AsyncMock(return_value={event_key}),
            ),
        ):
            await monitor._handle_user_fills(
                {"data": {"user": address, "isSnapshot": False, "fills": [fill]}}
            )

        self.assertEqual(sum(map(len, monitor._fill_buffer.values())), 1)

    async def test_failed_delivery_is_rescheduled_not_dropped(self) -> None:
        monitor = BlockchainMonitor(StubNotifier(succeeds=False))
        row = {
            "id": 7,
            "notification_key": "fill:key",
            "address": "0x" + "5" * 40,
            "notify_type": "fills",
            "message": "hello",
            "attempts": 0,
        }
        with (
            patch(
                "services.monitor.get_due_notifications", AsyncMock(return_value=[row])
            ),
            patch(
                "services.monitor.reschedule_notification", AsyncMock()
            ) as reschedule,
            patch("services.monitor.mark_notification_sent", AsyncMock()) as mark_sent,
        ):
            delivered = await monitor._deliver_due_notifications()

        self.assertEqual(delivered, 0)
        reschedule.assert_awaited_once()
        mark_sent.assert_not_awaited()

    async def test_successful_delivery_is_marked_sent(self) -> None:
        monitor = BlockchainMonitor(StubNotifier(succeeds=True))
        row = {
            "id": 8,
            "notification_key": "order:key",
            "address": "0x" + "6" * 40,
            "notify_type": "orders",
            "message": "hello",
            "attempts": 2,
        }
        with (
            patch(
                "services.monitor.get_due_notifications", AsyncMock(return_value=[row])
            ),
            patch(
                "services.monitor.reschedule_notification", AsyncMock()
            ) as reschedule,
            patch("services.monitor.mark_notification_sent", AsyncMock()) as mark_sent,
        ):
            delivered = await monitor._deliver_due_notifications()

        self.assertEqual(delivered, 1)
        mark_sent.assert_awaited_once_with(8)
        reschedule.assert_not_awaited()

    async def test_permanent_delivery_failure_is_archived(self) -> None:
        monitor = BlockchainMonitor(PermanentlyFailingNotifier())
        row = {
            "id": 10,
            "address": "0x" + "6" * 40,
            "notify_type": "orders",
            "message": "hello",
            "attempts": 0,
        }
        with (
            patch(
                "services.monitor.get_due_notifications", AsyncMock(return_value=[row])
            ),
            patch("services.monitor.mark_notification_failed", AsyncMock()) as failed,
            patch(
                "services.monitor.reschedule_notification", AsyncMock()
            ) as reschedule,
            patch("services.monitor.mark_notification_sent", AsyncMock()) as sent,
        ):
            delivered = await monitor._deliver_due_notifications()

        self.assertEqual(delivered, 0)
        failed.assert_awaited_once()
        reschedule.assert_not_awaited()
        sent.assert_not_awaited()

    async def test_realtime_capacity_is_enforced(self) -> None:
        monitor = BlockchainMonitor(StubNotifier())
        monitor._ws_tasks = {f"0x{index:040x}": object() for index in range(10)}
        with self.assertRaises(MonitorCapacityError):
            await monitor.subscribe("0x" + "f" * 40)

    async def test_first_order_recovery_establishes_baseline_without_alerts(
        self,
    ) -> None:
        address = "0x" + "7" * 40
        client = HistoricalClient([{"statusTimestamp": 100, "order": {"oid": 1}}])
        monitor = BlockchainMonitor(StubNotifier(), hl_client=client)
        with (
            patch("services.monitor.get_last_order_time", AsyncMock(return_value=0)),
            patch("services.monitor.update_last_order_time", AsyncMock()) as update,
        ):
            await monitor._recover_missed_orders(address)

        self.assertEqual(monitor._order_buffer, [])
        update.assert_awaited_once()

    async def test_order_recovery_replays_only_updates_after_cursor(self) -> None:
        address = "0x" + "8" * 40
        old = {
            "status": "filled",
            "statusTimestamp": 100,
            "order": {"oid": 1, "coin": "BTC", "limitPx": "10", "sz": "1"},
        }
        missed = {
            "status": "canceled",
            "statusTimestamp": 200,
            "order": {
                "oid": 2,
                "coin": "ETH",
                "limitPx": "20",
                "sz": "1",
                "orderType": "Limit",
            },
        }
        monitor = BlockchainMonitor(
            StubNotifier(), hl_client=HistoricalClient([missed, old])
        )
        event_key = monitor._order_event_key(address, missed)
        with (
            patch("services.monitor.get_last_order_time", AsyncMock(return_value=150)),
            patch(
                "services.monitor.get_unprocessed_event_keys",
                AsyncMock(return_value={event_key}),
            ),
        ):
            await monitor._recover_missed_orders(address)

        self.assertEqual(len(monitor._order_buffer), 1)
        self.assertEqual(monitor._order_buffer[0]["oid"], 2)
        self.assertEqual(monitor._order_buffer[0]["address_raw"], address)

    async def test_order_batch_folds_duplicate_oids_and_suppresses_redundant_fills(
        self,
    ) -> None:
        address = "0x" + "a" * 40
        monitor = BlockchainMonitor(StubNotifier())
        monitor._monitored_addresses = {address: {}}
        monitor._global_settings = {"notify_orders": True, "notify_fills": True}

        item_open = {
            "address": address,
            "address_display": address,
            "address_raw": address,
            "coin": "BTC",
            "dir": "Buy",
            "dir_badge": "🟢 买入",
            "status": "已挂单",
            "status_badge": "🟡 挂单中",
            "raw_status": "open",
            "limit_px": "100",
            "price": "$100.00",
            "sz": "1.0",
            "orig_sz": "1.0",
            "notional": "$100.00",
            "oid": 123,
            "reduce_only": "否",
            "order_type": "限价单",
            "time_in_force": "GTC",
            "time": "2026-08-17",
            "_event_key": "k1",
            "_event_time": 100,
        }
        item_filled = {
            "address": address,
            "address_display": address,
            "address_raw": address,
            "coin": "BTC",
            "dir": "Buy",
            "dir_badge": "🟢 买入",
            "status": "已成交",
            "status_badge": "🟢 全部成交",
            "raw_status": "filled",
            "limit_px": "100",
            "price": "$100.00",
            "sz": "0.0",
            "orig_sz": "1.0",
            "notional": "$100.00",
            "oid": 123,
            "reduce_only": "否",
            "order_type": "限价单",
            "time_in_force": "GTC",
            "time": "2026-08-17",
            "_event_key": "k2",
            "_event_time": 101,
        }

        # Case 1: When notify_fills is True, redundant filled status update is suppressed
        monitor._record_notification = AsyncMock()
        with (
            patch("services.monitor.record_events", AsyncMock()),
            patch("services.monitor.update_last_order_time", AsyncMock()),
        ):
            await monitor._send_order_batch([item_open, item_filled])

        monitor._record_notification.assert_not_awaited()

        # Case 2: When notify_fills is False, filled status update is delivered
        monitor._global_settings["notify_fills"] = False
        with (
            patch("services.monitor.record_events", AsyncMock(return_value=True)),
            patch("services.monitor.update_last_order_time", AsyncMock()),
        ):
            await monitor._send_order_batch([item_open, item_filled])

        monitor._record_notification.assert_awaited_once()
        msg = monitor._record_notification.await_args.args[3]
        self.assertIn("123", msg)
        self.assertIn("全部成交", msg)

    async def test_large_order_burst_becomes_one_readable_summary(self) -> None:
        address = "0x" + "c" * 40
        monitor = BlockchainMonitor(StubNotifier())
        monitor._record_notification = AsyncMock()
        items = []
        for index in range(200):
            is_cancel = index >= 100
            items.append(
                {
                    "address": address,
                    "address_display": f"<code>{address}</code>",
                    "address_raw": address,
                    "coin": "BTC",
                    "dir": "开空",
                    "dir_badge": "🔴 开空",
                    "status": "已撤销" if is_cancel else "挂单中",
                    "status_badge": "⚪ 已撤销" if is_cancel else "🟡 挂单中",
                    "raw_status": "canceled" if is_cancel else "open",
                    "limit_px": f"{100 + index}",
                    "price": f"${100 + index}.00",
                    "sz": "1.0000",
                    "orig_sz": "1.0000",
                    "notional": f"${100 + index}.00",
                    "oid": index + 1,
                    "reduce_only": "否",
                    "order_type": "限价单",
                    "time_in_force": "GTC",
                    "time": (
                        f"2026-08-21 18:{index // 60:02d}:{index % 60:02d} "
                        "UTC+08:00"
                    ),
                    "_event_key": f"order:{index}",
                    "_event_time": 100 + index,
                }
            )

        with patch("services.monitor.update_last_order_time", AsyncMock()):
            await monitor._send_order_notifications(items, "zh")

        monitor._record_notification.assert_awaited_once()
        args = monitor._record_notification.await_args.args
        self.assertEqual(len(args[0]), len(items))
        self.assertEqual(args[1], address)
        message = args[3]
        self.assertIn(f"订单批量变动汇总 ({len(items)} 笔)", message)
        self.assertIn(address, message)
        self.assertIn("🟡 挂单中", message)
        self.assertIn("⚪ 已撤销", message)
        self.assertEqual(message.count("100 笔"), 2)
        self.assertEqual(message.count("100 BTC"), 2)
        self.assertIn("$14,950.00", message)
        self.assertIn("$24,950.00", message)
        self.assertIn("$100.00 – $199.00", message)
        self.assertIn("$200.00 – $299.00", message)
        self.assertNotIn("订单 ID", message)


    async def test_order_updates_direction_smart_open_close(self) -> None:
        address = "0x" + "b" * 40
        monitor = BlockchainMonitor(StubNotifier())
        monitor._monitored_addresses = {address: {}}
        monitor._global_settings = {"notify_orders": True}

        # 1. Normal Buy -> 开多
        # 2. Reduce Buy -> 平空
        # 3. Normal Sell -> 开空
        # 4. Reduce Sell -> 平多
        orders_payload = [
            {
                "order": {
                    "coin": "ETH",
                    "side": "B",
                    "limitPx": "3000.0",
                    "sz": "1.0",
                    "origSz": "1.0",
                    "oid": 201,
                    "reduceOnly": False,
                    "orderType": "Limit",
                    "timestamp": 1723880000000,
                },
                "status": "open",
                "statusTimestamp": 1723880000000,
            },
            {
                "order": {
                    "coin": "ETH",
                    "side": "B",
                    "limitPx": "3000.0",
                    "sz": "1.0",
                    "origSz": "1.0",
                    "oid": 202,
                    "reduceOnly": True,
                    "orderType": "Stop Market",
                    "timestamp": 1723880000000,
                },
                "status": "open",
                "statusTimestamp": 1723880000000,
            },
            {
                "order": {
                    "coin": "SOL",
                    "side": "A",
                    "limitPx": "150.0",
                    "sz": "10.0",
                    "origSz": "10.0",
                    "oid": 203,
                    "reduceOnly": False,
                    "orderType": "Limit",
                    "timestamp": 1723880000000,
                },
                "status": "open",
                "statusTimestamp": 1723880000000,
            },
            {
                "order": {
                    "coin": "SOL",
                    "side": "A",
                    "limitPx": "150.0",
                    "sz": "10.0",
                    "origSz": "10.0",
                    "oid": 204,
                    "reduceOnly": True,
                    "orderType": "Limit",
                    "timestamp": 1723880000000,
                },
                "status": "open",
                "statusTimestamp": 1723880000000,
            },
        ]

        with patch("services.monitor.get_unprocessed_event_keys", AsyncMock(return_value=[
            monitor._order_event_key(address, o) for o in orders_payload
        ])):
            await monitor._handle_order_updates({"data": orders_payload}, source_address=address, allow_historical=True)

        self.assertEqual(len(monitor._order_buffer), 4)
        self.assertEqual(monitor._order_buffer[0]["dir"], "开多")
        self.assertEqual(monitor._order_buffer[0]["dir_badge"], "🟢 开多")

        self.assertEqual(monitor._order_buffer[1]["dir"], "平空")
        self.assertEqual(monitor._order_buffer[1]["dir_badge"], "🟢 平空")

        self.assertEqual(monitor._order_buffer[2]["dir"], "开空")
        self.assertEqual(monitor._order_buffer[2]["dir_badge"], "🔴 开空")

        self.assertEqual(monitor._order_buffer[3]["dir"], "平多")
        self.assertEqual(monitor._order_buffer[3]["dir_badge"], "🔴 平多")


if __name__ == "__main__":
    unittest.main()

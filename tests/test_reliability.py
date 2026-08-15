import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TG_BOT_TOKEN", "test-token")
os.environ.setdefault("TG_ADMIN_CHAT_ID", "1")
os.environ.setdefault("BOT_LANGUAGE", "zh")

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


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()

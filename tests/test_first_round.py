import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TG_BOT_TOKEN", "test-token")
os.environ.setdefault("TG_ADMIN_CHAT_ID", "1")
os.environ.setdefault("BOT_LANGUAGE", "zh")
os.environ.setdefault("DISPLAY_TIMEZONE", "Asia/Shanghai")

from core.config import settings
from infrastructure import db as database
from infrastructure.hl_client import HyperliquidClient
from services.monitor import BlockchainMonitor
from services.notifier import BaseNotifier
from tg_bot.formatting import (
    escape_html,
    format_address_display,
    format_crypto_amount,
    format_pnl,
    format_price,
    format_timestamp,
    format_usd,
    split_message,
)
from tg_bot.locales import (
    format_boolean,
    format_fill_badge,
    format_fill_direction,
    format_order_side,
    format_order_side_badge,
    format_order_status,
    format_order_status_badge,
    format_order_type,
    format_time_in_force,
    get_text,
)


class CapturingClient(HyperliquidClient):
    def __init__(self) -> None:
        super().__init__("https://example.invalid/info")
        self.payload = None

    async def _post(self, payload, user_address=""):
        self.payload = payload
        return [{"oid": 1, "orderType": "Limit"}]


class CapturingNotifier(BaseNotifier):
    def __init__(self) -> None:
        self.messages = []

    async def notify(self, message: str) -> bool:
        self.messages.append(message)
        return True


class FormattingTests(unittest.TestCase):
    def test_missing_order_type_is_explained(self) -> None:
        self.assertEqual(format_order_type(None, "zh"), "普通订单")
        self.assertNotIn("Unknown", format_order_type(None, "zh"))

    def test_order_labels_are_human_readable(self) -> None:
        self.assertEqual(format_order_type("Stop Market", "zh"), "止损市价单")
        self.assertEqual(format_order_type("Take Profit Market", "zh"), "止盈市价单")
        self.assertIn("仅挂单", format_time_in_force("Alo", "zh"))
        self.assertEqual(
            format_time_in_force(None, "zh", order_type="Stop Market"),
            "市价止损",
        )
        self.assertEqual(
            format_time_in_force(None, "zh", order_type="Take Profit Market"),
            "市价止盈",
        )
        self.assertEqual(format_time_in_force(None, "zh"), "一直有效 (GTC)")
        self.assertIn("保证金不足", format_order_status("marginCanceled", "zh"))
        self.assertEqual(format_order_side("invalid", "zh"), "未知方向")
        self.assertEqual(format_fill_direction("Open Long", "zh"), "开多")
        self.assertEqual(format_boolean(False, "zh", provided=False), "否")

    def test_html_and_time_are_safe_and_explicit(self) -> None:
        self.assertEqual(escape_html("<主力 & 观察>"), "&lt;主力 &amp; 观察&gt;")
        self.assertEqual(
            format_timestamp(1704067200000, "zh"),
            "2024-01-01 08:00:00 CST",
        )
        self.assertEqual(format_timestamp(0, "zh"), "未知时间")

    def test_long_messages_split_without_empty_or_oversized_chunks(self) -> None:
        chunks = split_message("a" * 11, max_length=5)
        self.assertEqual(chunks, ["a" * 5, "a" * 5, "a"])
        self.assertTrue(all(chunks))
        self.assertTrue(all(len(chunk) <= 5 for chunk in chunks))

    def test_new_formatting_helpers(self) -> None:
        # Address display
        self.assertEqual(
            format_address_display("0x1234567890abcdef1234567890abcdef12345678", "Whale", "zh"),
            "<b>Whale</b> (<code>0x1234567890abcdef1234567890abcdef12345678</code>)",
        )
        self.assertEqual(
            format_address_display("0x1234567890abcdef1234567890abcdef12345678", None, "zh"),
            "<code>0x1234567890abcdef1234567890abcdef12345678</code>",
        )

        # Price formatting
        self.assertEqual(format_price(65432.1), "$65,432.10")
        self.assertEqual(format_price(3.5), "$3.50")
        self.assertEqual(format_price(0.001234), "$0.001234")

        # Crypto amount formatting
        self.assertEqual(format_crypto_amount(1000.0), "1,000")
        self.assertEqual(format_crypto_amount(2.5000), "2.5")
        self.assertEqual(format_crypto_amount(0), "0")

        # PnL formatting
        self.assertIn("🟢", format_pnl(1234.56, "zh"))
        self.assertIn("+$1,234.56", format_pnl(1234.56, "zh"))
        self.assertIn("🔴", format_pnl(-500.0, "zh"))
        self.assertIn("-$500.00", format_pnl(-500.0, "zh"))

        # Badges
        self.assertEqual(format_fill_badge("Open Long", "zh"), "🟢 开多")
        self.assertEqual(format_fill_badge("Close Short", "zh"), "🟢 平空")
        self.assertEqual(format_fill_badge("Open Short", "zh"), "🔴 开空")
        self.assertEqual(format_fill_badge("Close Long", "zh"), "🔴 平多")
        self.assertEqual(format_order_side_badge("B", "zh"), "🟢 开多")
        self.assertEqual(format_order_side_badge("B", "zh", reduce_only=True), "🟢 平空")
        self.assertEqual(format_order_side_badge("A", "zh"), "🔴 开空")
        self.assertEqual(format_order_side_badge("A", "zh", reduce_only=True), "🔴 平多")
        self.assertEqual(format_order_side("B", "zh"), "开多")
        self.assertEqual(format_order_side("B", "zh", reduce_only=True), "平空")
        self.assertEqual(format_order_side("A", "zh"), "开空")
        self.assertEqual(format_order_side("A", "zh", reduce_only=True), "平多")
        self.assertIn("全部成交", format_order_status_badge("filled", "zh"))

    def test_alert_templates_first_line_intuitiveness(self) -> None:
        # tx_alert
        tx_msg = get_text(
            "zh",
            "tx_alert",
            dir_badge="🟢 开多",
            coin="BTC",
            notional="$50,000.00",
            address_display="<b>Whale</b> (<code>0x123...</code>)",
            price="5,000.00",
            size="0.7692",
            pnl_line="",
            fee="0.00",
            role="吃单方 (Taker)",
            time="2026-08-17 12:00:00 CST",
            extra_line="",
        )
        first_line = tx_msg.splitlines()[0]
        self.assertIn("🟢 开多 BTC", first_line)
        self.assertIn("$50,000.00", first_line)
        second_line = tx_msg.splitlines()[1]
        self.assertIn("Whale", second_line)

        # order_update_alert
        order_msg = get_text(
            "zh",
            "order_update_alert",
            status_badge="🟢 全部成交 (Filled)",
            coin="ETH",
            dir="买入",
            dir_badge="🟢 买入",
            address_display="<b>Whale</b> (<code>0x123...</code>)",
            price="$3,000.00",
            orig_sz="10",
            sz="0",
            notional="$50,000.00",
            order_type="限价单",
            time_in_force="一直有效，直到成交或撤销 (GTC)",
            reduce_only="否",
            time="2026-08-17 12:00:00 CST",
            oid=12345,
        )
        first_line_order = order_msg.splitlines()[0]
        self.assertIn("全部成交", first_line_order)
        self.assertIn("ETH", first_line_order)

    def test_single_info_per_line_formatting(self) -> None:
        order_alert = get_text(
            "zh",
            "order_update_alert",
            status_badge="🟡 挂单中",
            coin="BTC",
            dir="开多",
            dir_badge="🟢 开多",
            address_display="<code>0x123...</code>",
            price="0,000.00",
            orig_sz="1.5000",
            sz="1.5000",
            notional="0,000.00",
            order_type="限价单",
            time_in_force="一直有效 (GTC)",
            reduce_only="否",
            time="2026-08-17 14:00:00 CST",
            oid=999,
        )
        alert_lines = order_alert.splitlines()
        self.assertIn("🟡 挂单中", alert_lines[0])
        self.assertIn("BTC", alert_lines[0])
        self.assertIn("委托方向:</b> 🟢 开多", alert_lines[1])
        self.assertNotIn(" | ", order_alert)

        order_item = get_text(
            "zh",
            "order_update_item",
            status_badge="🟡 挂单中",
            coin="BTC",
            dir="开多",
            dir_badge="🟢 开多",
            address_display="<code>0x123...</code>",
            price="0,000.00",
            orig_sz="1.5000",
            sz="1.5000",
            notional="0,000.00",
            order_type="限价单",
            time_in_force="一直有效 (GTC)",
            reduce_only="否",
            time="2026-08-17 14:00:00 CST",
            oid=999,
        )
        self.assertNotIn(" | ", order_item)
        self.assertIn("委托方向:", order_item)
        self.assertIn("委托价格:", order_item)
        self.assertIn("剩余数量:", order_item)

        pos_detail = get_text(
            "zh",
            "position_detail",
            coin="BTC",
            pos_badge="🟢 多头",
            lev_val="10",
            lev_dir="全仓",
            szi="1.5",
            position_value="$90,000.00",
            entry_px="$60,000.00",
            liquidation_px="$50,000.00",
            upnl_display="+$1,000.00",
            roe_display="+10.00%",
            funding_all="-$5.00",
        )
        self.assertNotIn(" | ", pos_detail)
        self.assertIn("名义价值:", pos_detail)
        self.assertIn("回报率 (ROE):", pos_detail)



class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_orders_uses_frontend_endpoint(self) -> None:
        client = CapturingClient()
        result = await client.get_open_orders("0x" + "1" * 40)
        self.assertEqual(client.payload["type"], "frontendOpenOrders")
        self.assertEqual(result[0]["orderType"], "Limit")


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_order_status_uses_original_size_for_threshold(self) -> None:
        notifier = CapturingNotifier()
        monitor = BlockchainMonitor(notifier)
        address = "0x" + "1" * 40
        monitor._monitored_addresses = {address: {}}
        monitor._address_subscribed_at = {address: 0}
        monitor.min_notional_threshold = 1_000

        payload = {
            "data": [
                {
                    "status": "filled",
                    "statusTimestamp": 1_700_000_000_000,
                    "order": {
                        "coin": "BTC",
                        "side": "B",
                        "limitPx": "2000",
                        "sz": "0",
                        "origSz": "1",
                        "oid": 42,
                        "timestamp": 1_700_000_000_000,
                    },
                }
            ]
        }
        event_key = monitor._order_event_key(address, payload["data"][0])
        with patch(
            "services.monitor.get_unprocessed_event_keys",
            AsyncMock(return_value={event_key}),
        ):
            await monitor._handle_order_updates(payload, address)

        self.assertEqual(len(monitor._order_buffer), 1)
        item = monitor._order_buffer[0]
        self.assertEqual(item["order_type"], "普通订单")
        self.assertEqual(item["reduce_only"], "否")

    async def test_liquidation_schema_produces_alert(self) -> None:
        notifier = CapturingNotifier()
        monitor = BlockchainMonitor(notifier)
        address = "0x" + "2" * 40
        monitor._monitored_addresses = {address: {}}
        monitor._global_settings = {"notify_events": True}

        monitor._record_notification = AsyncMock(return_value=True)
        await monitor._handle_user_events(
            {
                "data": {
                    "liquidation": {
                        "lid": 7,
                        "liquidator": "0x" + "3" * 40,
                        "liquidated_user": address,
                        "liquidated_ntl_pos": "25000",
                        "liquidated_account_value": "500",
                    }
                }
            },
            address,
        )

        monitor._record_notification.assert_awaited_once()
        message = monitor._record_notification.await_args.args[3]
        self.assertIn("账户强平", message)
        self.assertIn("25,000.00", message)


@unittest.skipUnless(
    os.environ.get("RUN_DB_TESTS") == "1",
    "set RUN_DB_TESTS=1 in an environment that permits aiosqlite worker threads",
)
class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = settings.DB_PATH
        settings.DB_PATH = os.path.join(self.temp_dir.name, "test.db")
        await database.close_db()
        await database.init_db()

    async def asyncTearDown(self) -> None:
        await database.close_db()
        settings.DB_PATH = self.old_db_path
        self.temp_dir.cleanup()

    async def test_addresses_are_case_insensitive_and_normalized(self) -> None:
        mixed = "0x" + "Aa" * 20
        lower = mixed.lower()
        self.assertTrue(await database.add_address(mixed, "test"))
        self.assertFalse(await database.add_address(lower, "duplicate"))
        self.assertEqual(await database.get_addresses_with_notes(), [(lower, "test")])
        self.assertTrue(
            await database.update_note(mixed.upper().replace("0X", "0x"), "updated")
        )
        self.assertTrue(await database.remove_address(mixed))

    async def test_outbox_is_durable_and_idempotent(self) -> None:
        address = "0x" + "b" * 40
        events = [("fill:event-1", 100), ("fill:event-2", 100)]
        created = await database.record_events(
            events,
            notification_key="fills:batch-1",
            address=address,
            notify_type="fills",
            message="durable message",
        )
        duplicate = await database.record_events(
            events,
            notification_key="fills:batch-1",
            address=address,
            notify_type="fills",
            message="duplicate",
        )

        self.assertTrue(created)
        self.assertFalse(duplicate)
        due = await database.get_due_notifications()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["message"], "durable message")
        self.assertEqual(
            await database.get_unprocessed_event_keys(
                ["fill:event-1", "fill:event-2", "fill:event-3"]
            ),
            {"fill:event-3"},
        )

        await database.mark_notification_sent(due[0]["id"])
        self.assertEqual(await database.get_pending_notification_count(), 0)

    async def test_event_cursors_never_move_backwards(self) -> None:
        address = "0x" + "c" * 40
        self.assertTrue(await database.add_address(address))

        await database.update_last_fill_time(address, 200)
        await database.update_last_fill_time(address, 100)
        await database.update_last_order_time(address, 300)
        await database.update_last_order_time(address, 150)

        self.assertEqual(await database.get_last_fill_time(address), 200)
        self.assertEqual(await database.get_last_order_time(address), 300)

    async def test_permanent_outbox_failure_is_not_retried(self) -> None:
        await database.record_events(
            [("order:permanent-failure", 100)],
            notification_key="orders:permanent-failure",
            address="0x" + "d" * 40,
            notify_type="orders",
            message="invalid message",
        )
        due = await database.get_due_notifications()
        self.assertEqual(len(due), 1)

        await database.mark_notification_failed(due[0]["id"], "bad request")

        self.assertEqual(await database.get_due_notifications(), [])
        self.assertEqual(await database.get_pending_notification_count(), 0)


if __name__ == "__main__":
    unittest.main()

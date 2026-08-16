import logging
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "zh"})

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "welcome": (
            "👋 <b>Welcome to Hyperliquid Monitor!</b>\n\n"
            "An efficient, real-time address tracking assistant.\n\n"
            "➕ <b>1. Add & Remark (/add)</b>\n"
            "• Single: <code>/add &lt;address&gt; [note]</code>\n"
            "• Batch: <code>/add 0x111 Note A, 0x222 Note B</code>\n"
            "• Unified Note: <code>/add 0x111, 0x222 Group Note</code>\n\n"
            "➖ <b>2. Remove (/del)</b>\n"
            "• <code>/del &lt;address1&gt; &lt;address2&gt;</code>\n\n"
            "🗂 <b>3. Address Management Panel (/list)</b>\n"
            "• Interactive pagination: <code>/list</code> or <code>/list 2</code>\n"
            "• Search by note or address: <code>/list whale</code>\n"
            "• One-click Asset, Stats, Orders, Remarks & Settings\n\n"
            "🔔 <b>4. Alert Threshold Filter (/set_filter)</b>\n"
            "• <code>/set_filter 50000</code> - Only alert for &gt;= $50k notional\n"
            "• <code>/set_filter 0</code> - Disable filter (show all events)"
        ),
        "usage_add": "Usage: /add &lt;addr1, addr2...&gt; [optional note for all]",
        "batch_add_success": "✅ Successfully added {count} addresses.",
        "usage_del": "Usage: /del &lt;addr1, addr2...&gt;",
        "batch_del_success": "✅ Successfully removed {count} addresses.",
        "filter_usage": "Usage: /set_filter &lt;amount&gt;\nExample: /set_filter 50000\nSet to 0 to disable.",
        "filter_set": "✅ Global notification threshold set to ${amount}.",
        "filter_cleared": "✅ Global notification threshold has been disabled. All events will be shown.",
        "filter_current": "ℹ️ Current global notification threshold is ${amount}.",
        "filter_invalid": "❌ Invalid amount. Please enter a valid number.",
        "invalid_address": "❌ Invalid Address format. Please provide a 0x address.",
        "addr_unknown_multi": "Unknown (multiple addresses)",
        "add_success": "✅ Successfully added {address_display} to monitoring.",
        "add_exists": "⚠️ Address is already being monitored.",
        "del_success": "🗑️ Successfully removed {address_display} from monitoring.",
        "del_not_found": "⚠️ Address not found in monitoring list.",
        "list_empty": "📭 No addresses are currently being monitored.",
        "list_no_results": "🔍 No address or remark matched your search.",
        "list_header": "📋 <b>Monitored Addresses:</b>\n\n",
        "tx_alert": (
            "<b>{dir_badge} {coin}</b> · <b>{notional}</b>\n"
            "👤 {address_display}\n\n"
            "📊 <b>Avg Price:</b> <code>{price}</code>\n"
            "📦 <b>Total Size:</b> <code>{size} {coin}</code>\n"
            "💵 <b>Total Value:</b> <code>{notional}</code>\n"
            "{pnl_line}"
            "🏷️ <b>Fee:</b> <code>{fee}</code> ({role})\n"
            "🕒 <b>Time:</b> <code>{time}</code>\n"
            "{extra_line}"
        ),
        "order_update_alert": (
            "<b>{status_badge}</b> · <b>{coin}</b> {dir_badge}\n"
            "👤 {address_display}\n\n"
            "🎯 <b>Limit Price:</b> <code>{price}</code>\n"
            "📦 <b>Order Size:</b> <code>{orig_sz} {coin}</code> (<b>Remaining:</b> <code>{sz}</code>)\n"
            "💵 <b>Order Value:</b> <code>{notional}</code>\n"
            "⚙️ <b>Type:</b> <code>{order_type}</code> | <b>TIF:</b> <code>{time_in_force}</code>\n"
            "🛡️ <b>Reduce Only:</b> <code>{reduce_only}</code>\n"
            "🕒 <b>Time:</b> <code>{time}</code>\n"
            "🔗 <b>Order ID:</b> <code>#{oid}</code>"
        ),
        "order_updates_batch_alert": "📝 <b>Order Updates ({count})</b>\n\n{items}",
        "order_update_item": (
            "• <b>{status_badge}</b> · <b>{coin}</b> {dir_badge}\n"
            "  👤 {address_display}\n"
            "  🎯 <b>Price:</b> <code>{price}</code> | 📦 <b>Size:</b> <code>{orig_sz}</code> (Rem: <code>{sz}</code>) | 💵 <b>Val:</b> <code>{notional}</code>\n"
            "  ⚙️ <code>{order_type}</code> · <code>{time_in_force}</code> | 🛡️ <b>RO:</b> <code>{reduce_only}</code> | 🔗 <code>#{oid}</code>\n"
            "  🕒 <code>{time}</code>"
        ),
        "funding_alert": (
            "💸 <b>Funding Settlement</b> · <b>{coin}</b>\n"
            "👤 {address_display}\n\n"
            "💵 <b>Payment:</b> {payment_display}\n"
            "📦 <b>Position Size:</b> <code>{szi_display}</code>\n"
            "📈 <b>Funding Rate:</b> <code>{funding_rate}</code>\n"
            "🕒 <b>Time:</b> <code>{time}</code>"
        ),
        "event_alert": (
            "🚨 <b>Account Liquidation Alert</b>\n"
            "👤 {address_display}\n\n"
            "💥 <b>Liquidated Notional:</b> <code>{notional}</code>\n"
            "📉 <b>Account Value at Liq:</b> <code>{account_value}</code>\n"
            "⚖️ <b>Liquidator:</b> {liquidator}\n"
            "🕒 <b>Time:</b> <code>{time}</code>"
        ),
        "ledger_update_alert": (
            "🏦 <b>Ledger Update</b> · <b>{event_type}</b>\n"
            "👤 {address_display}\n\n"
            "💵 <b>Amount:</b> {amount_display}\n"
            "{hash_line}"
            "🕒 <b>Time:</b> <code>{time}</code>"
        ),
        "select_address": "👇 Please select an address to view:",
        "info_result": (
            "📊 <b>Account Overview & Positions</b>\n"
            "👤 {address_display}\n\n"
            "💰 <b>Assets Overview:</b>\n"
            "• <b>Total Equity:</b> <code>{equity}</code>\n"
            "• <b>Unrealized PnL:</b> {upnl}\n"
            "• <b>Withdrawable:</b> <code>{withdrawable}</code>\n"
            "• <b>Margin Used:</b> <code>{margin_used}</code>\n"
            "• <b>Total Notional:</b> <code>{total_ntl}</code>\n"
            "• <b>Maint Margin:</b> <code>{cross_maint}</code>\n"
            "• <b>Raw USD:</b> <code>{raw_usd}</code>\n\n"
            "📋 <b>Active Positions ({position_count}):</b>\n{positions}"
        ),
        "pos_long": "Long",
        "pos_short": "Short",
        "lev_cross": "Cross",
        "lev_isolated": "Isolated",
        "no_positions": "<i>No active positions.</i>",
        "position_detail": (
            "\n🔹 <b>{coin}</b> · {pos_badge} <b>{lev_val}x {lev_dir}</b>\n"
            "  • <b>Size:</b> <code>{szi} {coin}</code> (<b>Notional:</b> <code>{position_value}</code>)\n"
            "  • <b>Entry Price:</b> <code>{entry_px}</code> | <b>Liq Price:</b> <code>{liquidation_px}</code>\n"
            "  • <b>Unrealized PnL:</b> {upnl_display} (<b>ROE:</b> <code>{roe_display}</code>)\n"
            "  • <b>Cum. Funding:</b> <code>{funding_all}</code>\n"
        ),
        "orders_result": (
            "📋 <b>Active Orders</b> ({order_count})\n"
            "👤 {address_display}\n\n"
            "{orders}"
        ),
        "no_orders": "<i>No active open orders.</i>",
        "order_item": (
            "• <b>{coin}</b> {dir_badge} · <code>{order_type}</code>\n"
            "  🎯 <b>Price:</b> <code>{price}</code>\n"
            "  📦 <b>Size:</b> <code>{orig_sz} {coin}</code> (<b>Rem:</b> <code>{sz}</code>) · <b>Value:</b> <code>{notional}</code>\n"
            "  ⚙️ <b>TIF:</b> <code>{time_in_force}</code> | <b>Reduce Only:</b> <code>{reduce_only}</code>\n"
            "  🔗 <b>Order ID:</b> <code>#{oid}</code>\n\n"
        ),
        "stats_result": (
            "📈 <b>Historical Performance Stats</b>\n"
            "👤 {address_display}\n\n"
            "{stats}"
        ),
        "stats_item": (
            "⏱ <b>[{period}]</b>\n"
            "• <b>Realized PnL:</b> {pnl_formatted} (<b>ROI:</b> <code>{roi}</code>)\n"
            "• <b>Volume:</b> <code>{vol}</code>\n\n"
        ),
        "set_note_prompt": (
            "✏️ <b>Set Remark Note</b>\n\n"
            "👤 Address: {address_display}\n"
            "📝 Current Note: <code>{current_note}</code>\n\n"
            "👉 Please reply with the new note (max 32 chars), or send <code>-</code> to clear.\n"
            "Send /cancel to abort."
        ),
        "set_note_success": "✅ Remark updated for {address_display}!\n📝 New Note: <b>{note}</b>",
        "set_note_cleared": "🗑️ Remark cleared for {address_display}.",
        "set_note_cancelled": "❌ Remark update cancelled.",
        "note_too_long": "❌ Note too long. Maximum allowed length is {max_length} characters.",
        "delete_confirm": (
            "⚠️ <b>Confirm Removal</b>\n\n"
            "Are you sure you want to remove {address_display} from monitoring?"
        ),
        "delete_success": "🗑️ Successfully removed {address_display}.",
        "settings_user_title": (
            "⚙️ <b>Notification Settings</b>\n"
            "👤 {address_display}\n\n"
            "Toggle notifications for this address:"
        ),
        "settings_global_title": (
            "⚙️ <b>Global Notification Settings</b>\n\n"
            "Configure default notification channels:"
        ),
        "state_on": "✅ ON",
        "state_off": "❌ OFF",
        "state_global": "🌐 Global ({state})",
        "type_fills": "Trades (Fills)",
        "type_orders": "Order Updates",
        "type_fundings": "Funding Payments",
        "type_events": "Liquidations / Events",
        "type_ledger": "Transfers & Ledger",
        "btn_info": "📊 Assets & Positions",
        "btn_orders": "📋 Open Orders",
        "btn_stats": "📈 Performance Stats",
        "btn_note": "✏️ Set Remark",
        "btn_settings": "⚙️ Alert Settings",
        "btn_delete": "🗑️ Delete Address",
        "btn_back": "« Back to List",
        "btn_cancel": "❌ Cancel",
        "btn_confirm_delete": "⚠️ Confirm Delete",
        "fetch_failed": "❌ Failed to fetch data from Hyperliquid. Please retry.",
        "operation_failed": "❌ Operation failed. Please retry.",
        "ws_capacity_reached": "⚠️ Monitoring limit reached ({max_users} addresses). Running in polling mode for extra addresses.",
        "ws_capacity_startup": "⚠️ {count} addresses exceed WebSocket monitoring capacity ({max_users}). They will be updated via REST polling.",
    },
    "zh": {
        "welcome": (
            "👋 <b>欢迎使用 Hyperliquid 链上监控机器人！</b>\n\n"
            "高效、精准、零延迟的巨鲸与地址追踪助手。\n\n"
            "➕ <b>1. 添加与备注 (/add)</b>\n"
            "• 单个: <code>/add &lt;地址&gt; [备注]</code>\n"
            "• 批量独立备注: <code>/add 0x111 巨鲸A, 0x222 巨鲸B</code>\n"
            "• 批量统一备注: <code>/add 0x111, 0x222 聪明钱组</code>\n\n"
            "➖ <b>2. 移除监控 (/del)</b>\n"
            "• <code>/del &lt;地址1&gt; &lt;地址2&gt;</code>\n\n"
            "🗂 <b>3. 监控管理看板 (/list)</b>\n"
            "• 交互式翻页: <code>/list</code> 或 <code>/list 2</code>\n"
            "• 搜索备注或地址: <code>/list 巨鲸</code>\n"
            "• 一键查持仓、查挂单、查战绩、改备注、配告警\n\n"
            "🔔 <b>4. 全局告警金额过滤 (/set_filter)</b>\n"
            "• <code>/set_filter 50000</code> - 仅推送 &gt;= $50k 的事件\n"
            "• <code>/set_filter 0</code> - 停用过滤（推送所有变动）"
        ),
        "usage_add": "使用方法: /add &lt;地址1, 地址2...&gt; [统一备注]",
        "batch_add_success": "✅ 成功添加 {count} 个监控地址。",
        "usage_del": "使用方法: /del &lt;地址1, 地址2...&gt;",
        "batch_del_success": "✅ 成功移除 {count} 个监控地址。",
        "filter_usage": "使用方法: /set_filter &lt;金额&gt;\n例如: /set_filter 50000\n设为 0 则关闭过滤。",
        "filter_set": "✅ 全局推送过滤阈值已设置为 ${amount}。",
        "filter_cleared": "✅ 全局推送过滤已关闭，将推送所有交易与变动。",
        "filter_current": "ℹ️ 当前全局推送过滤阈值为 ${amount}。",
        "filter_invalid": "❌ 金额格式无效，请输入正确的数字。",
        "invalid_address": "❌ 地址格式错误，请输入有效的 0x 地址。",
        "addr_unknown_multi": "无法确定 (监控了多个地址)",
        "add_success": "✅ 成功添加监控: {address_display}",
        "add_exists": "⚠️ 该地址已在监控列表中。",
        "del_success": "🗑️ 已移除监控: {address_display}",
        "del_not_found": "⚠️ 监控列表中未找到该地址。",
        "list_empty": "📭 暂无监控地址，使用 /add 添加。",
        "list_no_results": "🔍 未找到匹配的地址或备注。",
        "list_header": "📋 <b>监控地址看板:</b>\n\n",
        "tx_alert": (
            "<b>{dir_badge} {coin}</b> · <b>{notional}</b>\n"
            "👤 {address_display}\n\n"
            "📊 <b>成交均价:</b> <code>{price}</code>\n"
            "📦 <b>成交数量:</b> <code>{size} {coin}</code>\n"
            "💵 <b>成交总额:</b> <code>{notional}</code>\n"
            "{pnl_line}"
            "🏷️ <b>手续费:</b> <code>{fee}</code> ({role})\n"
            "🕒 <b>成交时间:</b> <code>{time}</code>\n"
            "{extra_line}"
        ),
        "order_update_alert": (
            "<b>{status_badge}</b> · <b>{coin}</b> {dir_badge}\n"
            "👤 {address_display}\n\n"
            "🎯 <b>委托价格:</b> <code>{price}</code>\n"
            "📦 <b>委托数量:</b> <code>{orig_sz} {coin}</code> (<b>剩余:</b> <code>{sz}</code>)\n"
            "💵 <b>委托总额:</b> <code>{notional}</code>\n"
            "⚙️ <b>订单类型:</b> <code>{order_type}</code> | <b>有效方式:</b> <code>{time_in_force}</code>\n"
            "🛡️ <b>只减仓:</b> <code>{reduce_only}</code>\n"
            "🕒 <b>更新时间:</b> <code>{time}</code>\n"
            "🔗 <b>订单 ID:</b> <code>#{oid}</code>"
        ),
        "order_updates_batch_alert": "📝 <b>订单状态更新 ({count} 笔)</b>\n\n{items}",
        "order_update_item": (
            "• <b>{status_badge}</b> · <b>{coin}</b> {dir_badge}\n"
            "  👤 {address_display}\n"
            "  🎯 <b>价格:</b> <code>{price}</code> | 📦 <b>数量:</b> <code>{orig_sz}</code> (余: <code>{sz}</code>) | 💵 <b>总额:</b> <code>{notional}</code>\n"
            "  ⚙️ <code>{order_type}</code> · <code>{time_in_force}</code> | 🛡️ <b>只减仓:</b> <code>{reduce_only}</code> | 🔗 <code>#{oid}</code>\n"
            "  🕒 <code>{time}</code>"
        ),
        "funding_alert": (
            "💸 <b>资金费结算</b> · <b>{coin}</b>\n"
            "👤 {address_display}\n\n"
            "💵 <b>结算金额:</b> {payment_display}\n"
            "📦 <b>持仓规模:</b> <code>{szi_display}</code>\n"
            "📈 <b>资金费率:</b> <code>{funding_rate}</code>\n"
            "🕒 <b>结算时间:</b> <code>{time}</code>"
        ),
        "event_alert": (
            "🚨 <b>账户强平警报 (Liquidation)</b>\n"
            "👤 {address_display}\n\n"
            "💥 <b>被强平名义仓位:</b> <code>{notional}</code>\n"
            "📉 <b>强平时账户价值:</b> <code>{account_value}</code>\n"
            "⚖️ <b>清算方:</b> {liquidator}\n"
            "🕒 <b>发生时间:</b> <code>{time}</code>"
        ),
        "ledger_update_alert": (
            "🏦 <b>账户资金变动</b> · <b>{event_type}</b>\n"
            "👤 {address_display}\n\n"
            "💵 <b>变动金额:</b> {amount_display}\n"
            "{hash_line}"
            "🕒 <b>变动时间:</b> <code>{time}</code>"
        ),
        "select_address": "👇 请选择要查看或操作的地址：",
        "info_result": (
            "📊 <b>账户资产与持仓概览</b>\n"
            "👤 {address_display}\n\n"
            "💰 <b>资产总览 (Assets):</b>\n"
            "• <b>账户总权益:</b> <code>{equity}</code>\n"
            "• <b>未实现盈亏:</b> {upnl}\n"
            "• <b>可用提现:</b> <code>{withdrawable}</code>\n"
            "• <b>已用保证金:</b> <code>{margin_used}</code>\n"
            "• <b>持仓名义总值:</b> <code>{total_ntl}</code>\n"
            "• <b>维持保证金:</b> <code>{cross_maint}</code>\n"
            "• <b>原始 USD 余额:</b> <code>{raw_usd}</code>\n\n"
            "📋 <b>当前活跃持仓 ({position_count}):</b>\n{positions}"
        ),
        "pos_long": "多头 (Long)",
        "pos_short": "空头 (Short)",
        "lev_cross": "全仓 (Cross)",
        "lev_isolated": "逐仓 (Isolated)",
        "no_positions": "<i>当前无活跃持仓。</i>",
        "position_detail": (
            "\n🔹 <b>{coin}</b> · {pos_badge} <b>{lev_val}x {lev_dir}</b>\n"
            "  • <b>持仓数量:</b> <code>{szi} {coin}</code> (<b>名义价值:</b> <code>{position_value}</code>)\n"
            "  • <b>开仓均价:</b> <code>{entry_px}</code> | <b>预估强平:</b> <code>{liquidation_px}</code>\n"
            "  • <b>未实现盈亏:</b> {upnl_display} (<b>ROE:</b> <code>{roe_display}</code>)\n"
            "  • <b>累计已结资金费:</b> <code>{funding_all}</code>\n"
        ),
        "orders_result": (
            "📋 <b>当前挂单列表</b> ({order_count})\n"
            "👤 {address_display}\n\n"
            "{orders}"
        ),
        "no_orders": "<i>当前无活跃挂单。</i>",
        "order_item": (
            "• <b>{coin}</b> {dir_badge} · <code>{order_type}</code>\n"
            "  🎯 <b>价格:</b> <code>{price}</code>\n"
            "  📦 <b>数量:</b> <code>{orig_sz} {coin}</code> (<b>剩余:</b> <code>{sz}</code>) · <b>总额:</b> <code>{notional}</code>\n"
            "  ⚙️ <b>有效方式:</b> <code>{time_in_force}</code> | <b>只减仓:</b> <code>{reduce_only}</code>\n"
            "  🔗 <b>订单 ID:</b> <code>#{oid}</code>\n\n"
        ),
        "stats_result": (
            "📈 <b>历史交易表现统计</b>\n"
            "👤 {address_display}\n\n"
            "{stats}"
        ),
        "stats_item": (
            "⏱ <b>【{period}】</b>\n"
            "• <b>累计收益 (PnL):</b> {pnl_formatted} (<b>ROI:</b> <code>{roi}</code>)\n"
            "• <b>交易体量 (Vol):</b> <code>{vol}</code>\n\n"
        ),
        "set_note_prompt": (
            "✏️ <b>设置地址备注</b>\n\n"
            "👤 监控地址: {address_display}\n"
            "📝 当前备注: <code>{current_note}</code>\n\n"
            "👉 请直接回复新的备注名称（最多 32 字符），或发送 <code>-</code> 清除备注。\n"
            "发送 /cancel 可取消操作。"
        ),
        "set_note_success": "✅ 备注更新成功！\n👤 地址: {address_display}\n📝 新备注: <b>{note}</b>",
        "set_note_cleared": "🗑️ 备注已清除: {address_display}",
        "set_note_cancelled": "❌ 已取消备注修改。",
        "note_too_long": "❌ 备注过长，最多支持 {max_length} 个字符。",
        "delete_confirm": (
            "⚠️ <b>确认移除监控</b>\n\n"
            "确定要从监控列表中删除 {address_display} 吗？"
        ),
        "delete_success": "🗑️ 已成功移除: {address_display}",
        "settings_user_title": (
            "⚙️ <b>推送通知设置</b>\n"
            "👤 {address_display}\n\n"
            "单独控制此地址的消息推送开关："
        ),
        "settings_global_title": (
            "⚙️ <b>全局通知开关</b>\n\n"
            "配置默认的消息推送类别："
        ),
        "state_on": "✅ 开启",
        "state_off": "❌ 关闭",
        "state_global": "🌐 跟随全局 ({state})",
        "type_fills": "成交明细 (Fills)",
        "type_orders": "订单更新 (Orders)",
        "type_fundings": "资金费结算 (Funding)",
        "type_events": "强平与事件 (Events)",
        "type_ledger": "充提与划转 (Ledger)",
        "btn_info": "📊 资产与持仓",
        "btn_orders": "📋 当前挂单",
        "btn_stats": "📈 历史战绩",
        "btn_note": "✏️ 修改备注",
        "btn_settings": "⚙️ 推送配置",
        "btn_delete": "🗑️ 移除监控",
        "btn_back": "« 返回地址列表",
        "btn_cancel": "❌ 取消",
        "btn_confirm_delete": "⚠️ 确认删除",
        "fetch_failed": "❌ 获取 Hyperliquid 链上数据失败，请稍后重试。",
        "operation_failed": "❌ 操作执行失败，请稍后重试。",
        "ws_capacity_reached": "⚠️ 监控地址数量达到 WS 实时连接上限 ({max_users})，超出部分将自动采用轮询模式。",
        "ws_capacity_startup": "⚠️ 已监控地址中有 {count} 个超出 WebSocket 上限 ({max_users})，已自动转为 REST 轮询。",
    },
}

ORDER_STATUS_LABELS_ZH: dict[str, str] = {
    "open": "已挂单 (open)",
    "filled": "已成交 (filled)",
    "canceled": "已撤销 (canceled)",
    "cancelled": "已撤销 (cancelled)",
    "triggered": "已触发 (triggered)",
    "rejected": "已拒绝 (rejected)",
    "margincanceled": "保证金不足，已撤单 (marginCanceled)",
    "vaultwithdrawalcanceled": "金库提款导致撤单 (vaultWithdrawalCanceled)",
    "openinterestcapcanceled": "达到持仓上限，已撤单 (openInterestCapCanceled)",
    "selftradecanceled": "防止自成交，已撤单 (selfTradeCanceled)",
    "reduceonlycanceled": "无法继续减仓，已撤单 (reduceOnlyCanceled)",
    "siblingfilledcanceled": "关联止盈/止损已成交，已撤单 (siblingFilledCanceled)",
    "delistedcanceled": "资产下架，已撤单 (delistedCanceled)",
    "liquidatedcanceled": "账户强平，已撤单 (liquidatedCanceled)",
    "scheduledcancel": "定时撤单已触发 (scheduledCancel)",
    "tickrejected": "价格精度无效，已拒绝 (tickRejected)",
    "mintradentlrejected": "低于最小订单金额，已拒绝 (minTradeNtlRejected)",
    "perpmarginrejected": "保证金不足，已拒绝 (perpMarginRejected)",
    "reduceonlyrejected": "只减仓条件不成立，已拒绝 (reduceOnlyRejected)",
    "badalopxrejected": "仅挂单会立即成交，已拒绝 (badAloPxRejected)",
    "perpmaxpositionrejected": "超过合约最大持仓限制，已拒绝 (perpMaxPositionRejected)",
    "unknown": "未知状态",
}

ORDER_TYPE_LABELS_ZH: dict[str, str] = {
    "limit": "限价单",
    "market": "市价单",
    "stop limit": "止损限价单",
    "stop market": "止损市价单",
    "stop loss limit": "止损限价单",
    "stop loss market": "止损市价单",
    "take limit": "止盈限价单",
    "take market": "止盈市价单",
    "take profit limit": "止盈限价单",
    "take profit market": "止盈市价单",
    "trigger limit": "触发限价单",
    "trigger market": "触发市价单",
    "iceberg": "冰山委托",
    "twap": "TWAP委托",
    "trailing stop": "追踪止损单",
}

TIME_IN_FORCE_LABELS_ZH: dict[str, str] = {
    "alo": "仅挂单 (Post-Only / ALO)",
    "ioc": "立即成交或取消 (IOC)",
    "gtc": "一直有效直到取消 (GTC)",
    "frontendmarket": "前端市价有效 (Frontend Market)",
}

FILL_DIRECTION_LABELS_ZH: dict[str, str] = {
    "open long": "开多",
    "open_long": "开多",
    "close long": "平多",
    "close_long": "平多",
    "open short": "开空",
    "open_short": "开空",
    "close short": "平空",
    "close_short": "平空",
    "buy": "买入",
    "sell": "卖出",
}

LEDGER_EVENT_LABELS_ZH: dict[str, str] = {
    "deposit": "充值",
    "withdraw": "提现",
    "internaltransfer": "内部转账",
    "subaccounttransfer": "子账户转账",
    "liquidation": "强平结算",
    "vaultcreate": "创建金库",
    "vaultdeposit": "存入金库",
    "vaultdistribution": "金库分配",
    "vaultwithdraw": "金库提现",
    "vaultleadercommission": "金库主理人佣金",
    "spottransfer": "现货转账",
    "accountclasstransfer": "账户类型划转",
    "spotgenesis": "现货创世分配",
    "rewardsclaim": "领取奖励",
}


def _lang_code(lang_code: str) -> str:
    return "zh" if lang_code and "zh" in lang_code.lower() else "en"


def format_fill_badge(value: Any, lang_code: str = "zh") -> str:
    """Format fill direction with colored status emoji badge."""
    if not value:
        return "⚡ 未知方向" if _lang_code(lang_code) == "zh" else "⚡ Unknown"
    key = str(value).strip().lower()
    if _lang_code(lang_code) == "zh":
        badges = {
            "open long": "🟢 开多",
            "open_long": "🟢 开多",
            "close long": "🔴 平多",
            "close_long": "🔴 平多",
            "open short": "🔴 开空",
            "open_short": "🔴 开空",
            "close short": "🟢 平空",
            "close_short": "🟢 平空",
            "buy": "🟢 买入",
            "b": "🟢 买入",
            "sell": "🔴 卖出",
            "a": "🔴 卖出",
        }
        return badges.get(key, f"⚡ {value}")
    else:
        badges = {
            "open long": "🟢 Open Long",
            "open_long": "🟢 Open Long",
            "close long": "🔴 Close Long",
            "close_long": "🔴 Close Long",
            "open short": "🔴 Open Short",
            "open_short": "🔴 Open Short",
            "close short": "🟢 Close Short",
            "close_short": "🟢 Close Short",
            "buy": "🟢 Buy",
            "b": "🟢 Buy",
            "sell": "🔴 Sell",
            "a": "🔴 Sell",
        }
        return badges.get(key, f"⚡ {value}")


def format_order_side_badge(value: Any, lang_code: str = "zh") -> str:
    """Format order side (B/A) with colored emoji badge."""
    key = str(value).strip().upper() if value is not None else ""
    if _lang_code(lang_code) == "zh":
        if key in ("B", "BUY"):
            return "🟢 买入 / 做多"
        if key in ("A", "SELL"):
            return "🔴 卖出 / 做空"
        return "⚡ 未知方向"
    else:
        if key in ("B", "BUY"):
            return "🟢 Buy / Long"
        if key in ("A", "SELL"):
            return "🔴 Sell / Short"
        return "⚡ Unknown"


def format_order_status_badge(status: Any, lang_code: str = "zh") -> str:
    """Format order status with colored emoji badge."""
    key = str(status).strip().lower() if status else "unknown"
    if _lang_code(lang_code) == "zh":
        badges = {
            "open": "🟡 挂单中 (Open)",
            "filled": "🟢 全部成交 (Filled)",
            "canceled": "⚪ 已撤销 (Canceled)",
            "cancelled": "⚪ 已撤销 (Canceled)",
            "triggered": "🟣 已触发 (Triggered)",
            "rejected": "🔴 已拒绝 (Rejected)",
            "margincanceled": "🔴 保证金不足自动撤销 (Margin Canceled)",
        }
        return badges.get(key, f"⚡ {format_order_status(status, lang_code)}")
    else:
        badges = {
            "open": "🟡 Open",
            "filled": "🟢 Filled",
            "canceled": "⚪ Canceled",
            "cancelled": "⚪ Canceled",
            "triggered": "🟣 Triggered",
            "rejected": "🔴 Rejected",
            "margincanceled": "🔴 Margin Canceled",
        }
        return badges.get(key, f"⚡ {status if status else 'Unknown'}")


def format_order_status(status: Any, lang_code: str = "zh") -> str:
    """Human-readable order status in the target language."""
    if _lang_code(lang_code) == "zh":
        key = str(status).strip().lower() if status else "unknown"
        return ORDER_STATUS_LABELS_ZH.get(key, str(status) if status else "未知")
    return str(status) if status else "Unknown"


def format_order_type(value: Any, lang_code: str = "zh") -> str:
    """Human-readable order type / time-in-force in the target language."""
    if not value:
        return "接口未提供" if _lang_code(lang_code) == "zh" else "Not provided by API"
    if _lang_code(lang_code) == "zh":
        key = str(value).strip().lower()
        return ORDER_TYPE_LABELS_ZH.get(key, str(value))
    return str(value)


def format_time_in_force(
    value: Any,
    lang_code: str = "zh",
    *,
    order_type: Any = None,
) -> str:
    if not value:
        normalized_type = str(order_type or "").strip().lower()
        if "market" in normalized_type and any(
            marker in normalized_type
            for marker in ("stop", "take profit", "take", "trigger")
        ):
            readable_type = format_order_type(order_type, lang_code)
            if _lang_code(lang_code) == "zh":
                return f"不适用（{readable_type}触发后按市价执行）"
            return f"N/A ({readable_type} executes at market when triggered)"
        return "接口未提供" if _lang_code(lang_code) == "zh" else "Not provided by API"
    if _lang_code(lang_code) == "zh":
        key = str(value).strip().lower()
        return TIME_IN_FORCE_LABELS_ZH.get(key, str(value))
    return str(value)


def format_boolean(value: Any, lang_code: str = "zh", *, provided: bool = True) -> str:
    if not provided:
        return "接口未提供" if _lang_code(lang_code) == "zh" else "Not provided by API"
    if _lang_code(lang_code) == "zh":
        return "是" if bool(value) else "否"
    return "Yes" if bool(value) else "No"


def format_order_side(value: Any, lang_code: str = "zh") -> str:
    key = str(value).strip().upper() if value is not None else ""
    if key in ("B", "BUY"):
        return "买入 / 做多" if _lang_code(lang_code) == "zh" else "Buy"
    if key in ("A", "SELL"):
        return "卖出 / 做空" if _lang_code(lang_code) == "zh" else "Sell"
    return "未知方向" if _lang_code(lang_code) == "zh" else "Unknown side"


def format_fill_direction(value: Any, lang_code: str = "zh") -> str:
    if not value:
        return "未知方向" if _lang_code(lang_code) == "zh" else "Unknown direction"
    if _lang_code(lang_code) == "zh":
        return FILL_DIRECTION_LABELS_ZH.get(str(value).strip().lower(), str(value))
    return str(value)


def format_ledger_event(value: Any, lang_code: str = "zh") -> str:
    if not value:
        return (
            "未知账单类型" if _lang_code(lang_code) == "zh" else "Unknown ledger type"
        )
    if _lang_code(lang_code) == "zh":
        key = str(value).strip().lower()
        return LEDGER_EVENT_LABELS_ZH.get(key, str(value))
    return str(value)


def get_text(lang_code: str, key: str, **kwargs: Any) -> str:
    """Get a localized text string. Falls back to 'en' if key is missing."""
    lang = "zh" if lang_code and "zh" in lang_code.lower() else "en"
    text = MESSAGES.get(lang, MESSAGES["en"]).get(key, "")

    if not text:
        logger.warning("Missing locale key '%s' for language '%s'.", key, lang)
        return key

    if not kwargs:
        return text

    try:
        return text.format(**kwargs)
    except (KeyError, IndexError) as exc:
        logger.error(
            "Locale formatting error for key '%s' (lang=%s): %s", key, lang, exc
        )
        return text

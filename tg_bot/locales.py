import logging
from typing import Any, Dict, FrozenSet

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES: FrozenSet[str] = frozenset({"en", "zh"})

MESSAGES: Dict[str, Dict[str, str]] = {
    "en": {
        "welcome": (
            "👋 Welcome to Hyperliquid Monitor!\n\n"
            "Commands:\n"
            "/add &lt;address&gt; [note] - Add an address to monitor with an optional note\n"
            "/del &lt;address&gt; - Remove an address\n"
            "/list [query] - View and manage addresses (search or jump page)\n"
            "/set_filter &lt;amount&gt; - Set global dollar threshold for alerts"
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
        "add_success": "✅ Successfully added <code>{address}</code> to monitoring.",
        "add_exists": "⚠️ Address is already being monitored.",
        "del_success": "🗑️ Successfully removed <code>{address}</code> from monitoring.",
        "del_not_found": "⚠️ Address not found in monitoring list.",
        "list_empty": "📭 No addresses are currently being monitored.",
        "list_header": "📋 <b>Monitored Addresses:</b>\n\n",
        "tx_alert": (
            "🚨 Trade Alert\n"
            "Address: <code>{address}</code>\n"
            "Coin: {coin}\n"
            "Direction: {dir}\n"
            "Price: {price}\n"
            "Size: {size}\n"
            "Closed PnL: {closed_pnl}\n"
            "Fee: {fee}\n"
            "Role: {role}\n"
            "Order ID: {oid}\n"
            "Hash: {hash}\n"
            "Time: {time}"
        ),
        "order_update_alert": (
            "📝 Order Update\n"
            "Address: <code>{address}</code>\n"
            "Coin: {coin}\n"
            "Direction: {dir}\n"
            "Status: {status}\n"
            "Limit Px: {limit_px}\n"
            "Remaining Sz: {sz}\n"
            "Original Sz: {orig_sz}\n"
            "Order ID: {oid}\n"
            "Reduce Only: {reduce_only}\n"
            "Post Only: {post_only}\n"
            "Type: {order_type}\n"
            "Time: {time}"
        ),
        "order_updates_batch_alert": (
            "📝 Order Updates ({count})\n\n{items}"
        ),
        "order_update_item": (
            "• {coin} | {dir} | Status: {status}\n"
            "  Address: <code>{address}</code>\n"
            "  Limit Px: {limit_px} | Remaining: {sz} / Original: {orig_sz}\n"
            "  Order ID: {oid} | Reduce Only: {reduce_only} | Post Only: {post_only}\n"
            "  Type: {order_type}\n"
            "  Time: {time}"
        ),
        "funding_alert": (
            "💸 Funding Payment\n"
            "Address: <code>{address}</code>\n"
            "Coin: {coin}\n"
            "Payment: {payment}\n"
            "Position Sz: {szi}\n"
            "Funding Rate: {funding_rate}\n"
            "Time: {time}"
        ),
        "event_alert": (
            "⚠️ User Event\n"
            "Address: <code>{address}</code>\n"
            "Type: {event_type}\n"
            "Asset: {asset}\n"
            "{extra}"
            "Time: {time}"
        ),
        "ledger_update_alert": (
            "🏦 Ledger Update\n"
            "Address: <code>{address}</code>\n"
            "Type: {event_type}\n"
            "Amount: {amount}\n"
            "Hash: {hash}\n"
            "Time: {time}"
        ),
        "select_address": "👇 Please select an address to view:",
        "info_result": (
            "📊 <b>Account Info:</b> {address_display}\n\n"
            "💰 <b>Assets Overview:</b>\n"
            "<b>Total Equity:</b> ${equity}\n"
            "<b>Raw USD:</b> ${raw_usd}\n"
            "<b>Withdrawable:</b> ${withdrawable}\n"
            "<b>Total Notional:</b> ${total_ntl}\n\n"
            "🛡️ <b>Margin Status:</b>\n"
            "<b>Margin Used:</b> ${margin_used}\n"
            "<b>Cross Maint Margin:</b> ${cross_maint}\n"
            "<b>Unrealized PnL:</b> ${upnl}\n\n"
            "📋 <b>Active Positions:</b>\n{positions}"
        ),
        "pos_long": "Long",
        "pos_short": "Short",
        "lev_cross": "Cross",
        "lev_isolated": "Isolated",
        "position_detail": (
            "• <b>{coin}</b> | {pos_dir} {szi}\n"
            "  Lev: {lev_val}x ({lev_dir}) | Max: {max_leverage}x\n"
            "  Entry: {entry_px:.4f} | Liq: {liquidation_px:.4f}\n"
            "  Value: ${position_value:.2f}\n"
            "  uPnL: ${unrealized_pnl:.2f} (ROE: {roe:.2%})\n"
            "  Funding: ${funding_all:.2f}\n\n"
        ),
        "order_item": (
            "• <b>{coin}</b> | {dir}\n"
            "  Limit Px: {limit_px}\n"
            "  Size: {sz} / {orig_sz}\n"
            "  Order ID: {oid}\n"
            "  Reduce Only: {reduce_only}\n"
            "  Post Only: {post_only}\n"
            "  Type: {order_type}\n"
            "  Time: {time}\n\n"
        ),
        "orders_result": "📝 <b>Open Orders:</b> {address_display}\n\n{orders}",
        "btn_stats": "📊 Stats",
        "btn_info": "💰 Info",
        "btn_orders": "📜 Orders",
        "btn_note": "📝 Remark",
        "btn_delete": "🗑️ Delete",
        "delete_success": "✅ Successfully removed {address}.",
        "btn_back": "🔙 Back",
        "stats_result": "📊 <b>Performance Stats:</b> {address_display}\n\n{stats}",
        "stats_item": "<b>{period}</b>\nPnL: {pnl} (ROI: {roi})\nVolume: {vol}\n\n",
        "no_positions": "No active positions.",
        "no_orders": "No open orders.",
        "fetch_failed": "❌ Failed to fetch data. Please try again.",
        "set_note_prompt": "Please reply to this message with the remark for address <code>{address}</code>.\n(Send <code>-</code> to clear the remark, or <code>/cancel</code> to cancel)",
        "set_note_success": "✅ Remark for <code>{address}</code> has been updated.",
        "set_note_cleared": "✅ Remark for <code>{address}</code> has been cleared.",
        "set_note_cancelled": "🚫 Operation cancelled.",
        "settings_global_title": "⚙️ <b>Global Notification Settings</b>\nToggle global alerts below. These act as defaults for all monitored addresses.",
        "settings_user_title": "⚙️ <b>Address Notification Settings</b>\n<code>{address}</code>\nConfigure overrides for this specific address.",
        "btn_settings": "⚙️ Settings",
        "type_fills": "Fills",
        "type_orders": "Orders",
        "type_events": "Events",
        "type_fundings": "Fundings",
        "type_ledger": "Ledger",
        "state_on": "✅ ON",
        "state_off": "❌ OFF",
        "state_global": "🌐 Global",
    },
    "zh": {
        "welcome": (
            "👋 <b>欢迎使用 Hyperliquid Monitor！</b>\n\n"
            "我是一个专为高效而生的地址追踪助手。以下是我的全部超能力：\n\n"
            
            "➕ <b>1. 极速添加与备注 (/add)</b>\n"
            "你可以随时输入 <code>/add &lt;地址&gt;</code> 来监控一个钱包，但我支持更多高端玩法：\n"
            "• <b>单次加备注</b>：<code>/add 0x123... 巨鲸1号</code>\n"
            "• <b>批量精细备注</b>：<code>/add 0x111 玩家A, 0x222 玩家B</code> (逗号或空格隔开都行)\n"
            "• <b>批量统一备注</b>：发一堆地址，只在末尾写一句话，比如 <code>/add 0x111, 0x222, 0x333 顶级胜率组合</code>，我会把这个备注赋予前面的所有地址！\n\n"
            
            "➖ <b>2. 批量移除 (/del)</b>\n"
            "想删就删，毫不拖泥带水：\n"
            "• <b>单个删除</b>：<code>/del 0x123...</code>\n"
            "• <b>批量删除</b>：直接丢一堆地址给我 <code>/del 0x111 0x222 0x333</code>，瞬间清理干净。\n\n"
            
            "🗂 <b>3. 智能地址库面板 (/list)</b>\n"
            "我的核心控制台，告别繁琐的命令：\n"
            "• <b>无缝翻页</b>：采用 10 项/页 的精美面板。你可以点击底部的 ⬅️ ➡️，也可以直接输入 <code>/list 3</code> 飞跃到第 3 页。\n"
            "• <b>全局搜索</b>：忘了地址？没关系。输入 <code>/list 巨鲸</code>，我会瞬间筛选出名字或地址里带有该词的所有记录！\n"
            "• <b>一站式操作</b>：点击面板里的任何地址，你会看到详细的 资产、战绩、挂单... 并且，你可以直接在详情页点击 <b>[📝修改备注]</b> 甚至是 <b>[🗑️移除地址]</b>，操作完后自动退回列表页，永远不会迷路。\n\n"
            
            "🔔 <b>4. 通知阈值过滤 (/set_filter)</b>\n"
            "受够了微小的变动推送？\n"
            "• 输入 <code>/set_filter 50000</code>，只有金额变动超过 $50,000 才会打扰你。\n"
            "• 输入 <code>/set_filter 0</code>，则关闭过滤，全量推送。\n\n"
            
            "💡 <b>隐藏细节</b>：\n"
            "遇到长名字或者手机排版问题？别担心，我内置了<b>智能折叠排版</b>，而且所有的十六进制 0x 地址，都可以点击一键复制！"
        ),
        "usage_add": "用法: /add &lt;地址1,地址2...&gt; [可选统一备注]",
        "batch_add_success": "✅ 成功批量添加了 {count} 个地址。",
        "usage_del": "用法: /del &lt;地址1,地址2...&gt;",
        "batch_del_success": "✅ 成功批量移除了 {count} 个地址。",
        "filter_usage": "用法: /set_filter <金额>\n示例: /set_filter 50000\n设置为 0 可以完全关闭过滤功能。",
        "filter_set": "✅ 已成功将全局通知资金阈值设置为 ${amount}。低于此美金价值的变动将不会通知。",
        "filter_cleared": "✅ 已关闭资金阈值过滤。现在将推送所有通知。",
        "filter_current": "ℹ️ 当前全局资金过滤阈值为 ${amount}。",
        "filter_invalid": "❌ 无效的金额，请输入一个纯数字。",
        "invalid_address": "❌ 地址格式无效，请提供 0x 开头的地址。",
        "addr_unknown_multi": "无法确定 (监控了多个地址)",
        "add_success": "✅ 已成功将 <code>{address}</code> 加入监控。",
        "add_exists": "⚠️ 该地址已经在监控列表中。",
        "del_success": "🗑️ 已成功将 <code>{address}</code> 移出监控。",
        "del_not_found": "⚠️ 监控列表中未找到该地址。",
        "list_empty": "📭 当前没有监控任何地址。",
        "list_header": "📋 <b>当前监控地址：</b>\n\n",
        "tx_alert": (
            "🚨 交易提醒\n"
            "地址: <code>{address}</code>\n"
            "币种: {coin}\n"
            "方向: {dir}\n"
            "价格: {price}\n"
            "数量: {size}\n"
            "平仓盈亏: {closed_pnl}\n"
            "手续费: {fee}\n"
            "成交角色: {role}\n"
            "订单 ID: {oid}\n"
            "交易哈希: {hash}\n"
            "成交时间: {time}"
        ),
        "order_update_alert": (
            "📝 订单状态更新\n"
            "地址: <code>{address}</code>\n"
            "币种: {coin}\n"
            "方向: {dir}\n"
            "当前状态: {status}\n"
            "限价: {limit_px}\n"
            "当前剩余数量: {sz}\n"
            "初始委托数量: {orig_sz}\n"
            "订单 ID: {oid}\n"
            "只减仓: {reduce_only}\n"
            "被动委托: {post_only}\n"
            "订单类型: {order_type}\n"
            "更新时间: {time}"
        ),
        "order_updates_batch_alert": (
            "📝 订单状态更新 (共 {count} 条)\n\n{items}"
        ),
        "order_update_item": (
            "• {coin} | {dir} | 状态: {status}\n"
            "  地址: <code>{address}</code>\n"
            "  限价: {limit_px} | 剩余: {sz} / 初始: {orig_sz}\n"
            "  订单 ID: {oid} | 只减仓: {reduce_only} | 被动: {post_only}\n"
            "  订单类型: {order_type}\n"
            "  时间: {time}"
        ),
        "funding_alert": (
            "💸 资金费率结算\n"
            "地址: <code>{address}</code>\n"
            "币种: {coin}\n"
            "结算金额: {payment}\n"
            "当时持仓数量: {szi}\n"
            "实际资金费率: {funding_rate}\n"
            "结算时间: {time}"
        ),
        "event_alert": (
            "⚠️ 账户重大事件\n"
            "地址: <code>{address}</code>\n"
            "事件类型: {event_type}\n"
            "相关资产: {asset}\n"
            "{extra}"
            "发生时间: {time}"
        ),
        "ledger_update_alert": (
            "🏦 内部账单变动\n"
            "地址: <code>{address}</code>\n"
            "变动类型: {event_type}\n"
            "金额变动: {amount}\n"
            "区块哈希: {hash}\n"
            "处理时间: {time}"
        ),
        "select_address": "👇 请选择你要查看的地址：",
        "info_result": (
            "📊 <b>账户详情:</b> {address_display}\n\n"
            "💰 <b>资产概览:</b>\n"
            "<b>总权益 (Equity):</b> ${equity}\n"
            "<b>可用资金 (Raw USD):</b> ${raw_usd}\n"
            "<b>可提现 (Withdrawable):</b> ${withdrawable}\n"
            "<b>总名义价值 (Notional):</b> ${total_ntl}\n\n"
            "🛡️ <b>保证金状态:</b>\n"
            "<b>已用保证金:</b> ${margin_used}\n"
            "<b>全仓维持保证金:</b> ${cross_maint}\n"
            "<b>未实现盈亏:</b> ${upnl}\n\n"
            "📋 <b>当前持仓:</b>\n{positions}"
        ),
        "pos_long": "多头 (Long)",
        "pos_short": "空头 (Short)",
        "lev_cross": "全仓",
        "lev_isolated": "逐仓",
        "position_detail": (
            "• <b>{coin}</b> | {pos_dir} {szi}\n"
            "  杠杆: {lev_val}x ({lev_dir}) | 最大: {max_leverage}x\n"
            "  开仓价: {entry_px:.4f} | 强平价: {liquidation_px:.4f}\n"
            "  名义价值: ${position_value:.2f}\n"
            "  未实现盈亏: ${unrealized_pnl:.2f} (ROE: {roe:.2%})\n"
            "  累计资金费: ${funding_all:.2f}\n\n"
        ),
        "order_item": (
            "• <b>{coin}</b> | {dir}\n"
            "  限价: {limit_px}\n"
            "  剩余数量: {sz} (初始数量: {orig_sz})\n"
            "  订单 ID: {oid}\n"
            "  只减仓: {reduce_only}\n"
            "  被动委托: {post_only}\n"
            "  订单类型: {order_type}\n"
            "  下单时间: {time}\n\n"
        ),
        "orders_result": "📝 <b>当前挂单:</b> {address_display}\n\n{orders}",
        "btn_stats": "📊 历史战绩",
        "btn_info": "💰 资产持仓",
        "btn_orders": "📜 当前挂单",
        "btn_note": "📝 修改备注",
        "btn_delete": "🗑️ 移除地址",
        "delete_success": "✅ 已成功移除地址 {address}。",
        "btn_back": "🔙 返回列表",
        "stats_result": "📊 <b>历史战绩:</b> {address_display}\n\n{stats}",
        "stats_item": "<b>【{period}】</b>\n净盈亏: {pnl} (ROI: {roi})\n交易量: {vol}\n\n",
        "no_positions": "暂无活跃持仓。",
        "no_orders": "暂无挂单。",
        "fetch_failed": "❌ 获取数据失败，请稍后再试。",
        "set_note_prompt": "👇 请直接发送你想为地址 <code>{address}</code> 设置的备注内容。\n（发送 <code>-</code> 减号清空备注，发送 <code>/cancel</code> 取消操作）",
        "set_note_success": "✅ 地址 <code>{address}</code> 的备注已更新。",
        "set_note_cleared": "✅ 地址 <code>{address}</code> 的备注已清空。",
        "set_note_cancelled": "🚫 操作已取消。",
        "settings_global_title": "⚙️ <b>全局通知设置</b>\n在此统一管理各类通知的全局开关。该设置将作为所有地址的默认行为。",
        "settings_user_title": "⚙️ <b>独立通知设置</b>\n<code>{address}</code>\n在此为该地址进行精细控制。开启或关闭将无视全局设置。",
        "btn_settings": "⚙️ 通知设置",
        "type_fills": "成交",
        "type_orders": "订单",
        "type_events": "事件",
        "type_fundings": "资金费",
        "type_ledger": "内部账单",
        "state_on": "✅ 开启",
        "state_off": "❌ 关闭",
        "state_global": "🌐 跟随全局",
    },
}


def _lang_code(lang_code: str) -> str:
    """Normalize a language code to 'zh' or 'en' (mirrors get_text)."""
    return "zh" if lang_code and "zh" in lang_code.lower() else "en"


ORDER_STATUS_LABELS_ZH: Dict[str, str] = {
    "open": "已挂单 (open)",
    "filled": "已成交 (filled)",
    "canceled": "已撤销 (canceled)",
    "cancelled": "已撤销 (cancelled)",
    "triggered": "已触发 (triggered)",
    "rejected": "已拒绝 (rejected)",
    "unknown": "未知 (unknown)",
}

ORDER_TYPE_LABELS_ZH: Dict[str, str] = {
    "limit": "限价单",
    "market": "市价单",
    "stop limit": "止损限价单",
    "stop market": "止损市价单",
    "trigger limit": "触发限价单",
    "trigger market": "触发市价单",
    "iceberg": "冰山委托",
    "alo": "主动挂单",
    "ioc": "立即成交或取消",
    "gtc": "一直有效",
}


def format_order_status(status: Any, lang_code: str = "zh") -> str:
    """Human-readable order status in the target language.

    Hyperliquid returns raw values like ``open`` / ``filled`` / ``canceled``;
    in Chinese these are translated (with the original kept in parentheses).
    """
    if _lang_code(lang_code) == "zh":
        key = str(status).strip().lower() if status else "unknown"
        return ORDER_STATUS_LABELS_ZH.get(key, str(status) if status else "Unknown")
    return str(status) if status else "Unknown"


def format_order_type(value: Any, lang_code: str = "zh") -> str:
    """Human-readable order type / time-in-force in the target language.

    Hyperliquid order updates expose the order type via ``orderType``
    (e.g. ``Limit``, ``Stop Market``); ``tif`` values (``Alo``/``Ioc``/``Gtc``)
    are also understood.
    """
    if not value:
        return "Unknown"
    if _lang_code(lang_code) == "zh":
        key = str(value).strip().lower()
        return ORDER_TYPE_LABELS_ZH.get(key, str(value))
    return str(value)


def get_text(lang_code: str, key: str, **kwargs: Any) -> str:
    """Get a localized text string. Falls back to 'en' if key is missing.

    Template formatting errors (e.g. mismatched placeholders) are caught
    and logged instead of propagating as unhandled exceptions.
    """
    # Resolve language: recognise any zh variant, otherwise English.
    lang = "zh" if lang_code and "zh" in lang_code.lower() else "en"
    text = MESSAGES.get(lang, MESSAGES["en"]).get(key, "")

    if not text:
        logger.warning("Missing locale key '%s' for language '%s'.", key, lang)
        return key  # Return the raw key so the caller has *something*.

    if not kwargs:
        return text

    try:
        return text.format(**kwargs)
    except (KeyError, IndexError) as exc:
        logger.error(
            "Locale formatting error for key '%s' (lang=%s): %s", key, lang, exc
        )
        return text  # Return un-substituted template rather than crashing.

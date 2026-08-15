import logging
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "zh"})

MESSAGES: dict[str, dict[str, str]] = {
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
        "list_no_results": "🔍 No address or remark matched your search.",
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
            "Type: {order_type}\n"
            "Time in Force: {time_in_force}\n"
            "Reduce Only: {reduce_only}\n"
            "Time: {time}"
        ),
        "order_updates_batch_alert": ("📝 Order Updates ({count})\n\n{items}"),
        "order_update_item": (
            "• {coin} | {dir} | Status: {status}\n"
            "  Address: <code>{address}</code>\n"
            "  Limit Px: {limit_px} | Remaining: {sz} / Original: {orig_sz}\n"
            "  Order ID: {oid} | Reduce Only: {reduce_only}\n"
            "  Type: {order_type} | TIF: {time_in_force}\n"
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
            "  Entry: {entry_px} | Liq: {liquidation_px}\n"
            "  Value: ${position_value:.2f}\n"
            "  uPnL: ${unrealized_pnl:.2f} (ROE: {roe:.2%})\n"
            "  Funding: ${funding_all:.2f}\n\n"
        ),
        "order_item": (
            "• <b>{coin}</b> | {dir}\n"
            "  Limit Px: {limit_px}\n"
            "  Size: {sz} / {orig_sz}\n"
            "  Order ID: {oid}\n"
            "  Type: {order_type}\n"
            "  Time in Force: {time_in_force}\n"
            "  Reduce Only: {reduce_only}\n"
            "  Trigger: {trigger_condition}\n"
            "  Trigger Px: {trigger_px}\n"
            "  Position TP/SL: {position_tpsl}\n"
            "  Time: {time}\n\n"
        ),
        "orders_result": "📝 <b>Open Orders:</b> {address_display}\n\n{orders}",
        "btn_stats": "📊 Stats",
        "btn_info": "💰 Info",
        "btn_orders": "📜 Orders",
        "btn_note": "📝 Remark",
        "btn_delete": "🗑️ Delete",
        "delete_success": "✅ Successfully removed {address}.",
        "delete_confirm": "⚠️ Remove <code>{address}</code> from monitoring? This does not affect the wallet itself.",
        "btn_confirm_delete": "✅ Confirm removal",
        "btn_cancel": "Cancel",
        "btn_back": "🔙 Back",
        "stats_result": "📊 <b>Performance Stats:</b> {address_display}\n\n{stats}",
        "stats_item": "<b>{period}</b>\nPnL: {pnl} (ROI: {roi})\nVolume: {vol}\n\n",
        "no_positions": "No active positions.",
        "no_orders": "No open orders.",
        "fetch_failed": "❌ Failed to fetch data. Please try again.",
        "operation_failed": "❌ Operation failed. Nothing was changed; please try again.",
        "ws_capacity_reached": "❌ Hyperliquid allows at most {limit} realtime addresses per IP. Remove an address before adding another.",
        "ws_capacity_startup": "⚠️ Hyperliquid realtime limit reached: {active} addresses are active and {skipped} are inactive. Remove an active address to promote the next one.",
        "set_note_prompt": "Please reply to this message with the remark for address <code>{address}</code>.\n(Send <code>-</code> to clear the remark, or <code>/cancel</code> to cancel)",
        "set_note_success": "✅ Remark for <code>{address}</code> has been updated.",
        "set_note_cleared": "✅ Remark for <code>{address}</code> has been cleared.",
        "set_note_cancelled": "🚫 Operation cancelled.",
        "note_too_long": "❌ Remark is too long. Please keep it within {max_length} characters.",
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
        "list_no_results": "🔍 没有找到匹配的地址或备注。",
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
            "订单类型: {order_type}\n"
            "有效方式: {time_in_force}\n"
            "只减仓: {reduce_only}\n"
            "更新时间: {time}"
        ),
        "order_updates_batch_alert": ("📝 订单状态更新 (共 {count} 条)\n\n{items}"),
        "order_update_item": (
            "• {coin} | {dir} | 状态: {status}\n"
            "  地址: <code>{address}</code>\n"
            "  限价: {limit_px} | 剩余: {sz} / 初始: {orig_sz}\n"
            "  订单 ID: {oid} | 只减仓: {reduce_only}\n"
            "  订单类型: {order_type} | 有效方式: {time_in_force}\n"
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
            "  开仓价: {entry_px} | 强平价: {liquidation_px}\n"
            "  名义价值: ${position_value:.2f}\n"
            "  未实现盈亏: ${unrealized_pnl:.2f} (ROE: {roe:.2%})\n"
            "  累计资金费: ${funding_all:.2f}\n\n"
        ),
        "order_item": (
            "• <b>{coin}</b> | {dir}\n"
            "  限价: {limit_px}\n"
            "  剩余数量: {sz} (初始数量: {orig_sz})\n"
            "  订单 ID: {oid}\n"
            "  订单类型: {order_type}\n"
            "  有效方式: {time_in_force}\n"
            "  只减仓: {reduce_only}\n"
            "  触发条件: {trigger_condition}\n"
            "  触发价格: {trigger_px}\n"
            "  仓位止盈止损: {position_tpsl}\n"
            "  下单时间: {time}\n\n"
        ),
        "orders_result": "📝 <b>当前挂单:</b> {address_display}\n\n{orders}",
        "btn_stats": "📊 历史战绩",
        "btn_info": "💰 资产持仓",
        "btn_orders": "📜 当前挂单",
        "btn_note": "📝 修改备注",
        "btn_delete": "🗑️ 移除地址",
        "delete_success": "✅ 已成功移除地址 {address}。",
        "delete_confirm": "⚠️ 确定将 <code>{address}</code> 移出监控吗？此操作不会影响钱包本身。",
        "btn_confirm_delete": "✅ 确认移除",
        "btn_cancel": "取消",
        "btn_back": "🔙 返回列表",
        "stats_result": "📊 <b>历史战绩:</b> {address_display}\n\n{stats}",
        "stats_item": "<b>【{period}】</b>\n净盈亏: {pnl} (ROI: {roi})\n交易量: {vol}\n\n",
        "no_positions": "暂无活跃持仓。",
        "no_orders": "暂无挂单。",
        "fetch_failed": "❌ 获取数据失败，请稍后再试。",
        "operation_failed": "❌ 操作失败，数据未被修改，请稍后重试。",
        "ws_capacity_reached": "❌ Hyperliquid 每个 IP 最多允许实时监控 {limit} 个地址。请先移除一个地址再添加。",
        "ws_capacity_startup": "⚠️ 已达到 Hyperliquid 实时监控上限：{active} 个地址正在监控，另有 {skipped} 个地址暂未启用。移除活跃地址后会自动补位。",
        "set_note_prompt": "👇 请直接发送你想为地址 <code>{address}</code> 设置的备注内容。\n（发送 <code>-</code> 减号清空备注，发送 <code>/cancel</code> 取消操作）",
        "set_note_success": "✅ 地址 <code>{address}</code> 的备注已更新。",
        "set_note_cleared": "✅ 地址 <code>{address}</code> 的备注已清空。",
        "set_note_cancelled": "🚫 操作已取消。",
        "note_too_long": "❌ 备注过长，请控制在 {max_length} 个字符以内。",
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
    "ioccancelrejected": "IOC 无法成交，已取消 (iocCancelRejected)",
    "badtriggerpxrejected": "止盈/止损触发价无效，已拒绝 (badTriggerPxRejected)",
    "marketordernoliquidityrejected": "市价单流动性不足，已拒绝 (marketOrderNoLiquidityRejected)",
    "positionincreaseatopeninterestcaprejected": "达到持仓上限，禁止加仓 (positionIncreaseAtOpenInterestCapRejected)",
    "positionflipatopeninterestcaprejected": "达到持仓上限，禁止反向开仓 (positionFlipAtOpenInterestCapRejected)",
    "tooaggressiveatopeninterestcaprejected": "达到持仓上限且价格过激，已拒绝 (tooAggressiveAtOpenInterestCapRejected)",
    "openinterestincreaserejected": "禁止增加未平仓量，已拒绝 (openInterestIncreaseRejected)",
    "insufficientspotbalancerejected": "现货余额不足，已拒绝 (insufficientSpotBalanceRejected)",
    "oraclerejected": "价格偏离预言机，已拒绝 (oracleRejected)",
    "perpmaxpositionrejected": "超过永续合约最大仓位，已拒绝 (perpMaxPositionRejected)",
    "unknown": "未知 (unknown)",
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
}

TIME_IN_FORCE_LABELS_ZH: dict[str, str] = {
    "alo": "仅挂单 / 只做 Maker (ALO)",
    "ioc": "立即成交，否则取消 (IOC)",
    "gtc": "一直有效，直到成交或撤销 (GTC)",
    "frontendmarket": "前端市价执行 (FrontendMarket)",
}

FILL_DIRECTION_LABELS_ZH: dict[str, str] = {
    "open long": "开多",
    "close long": "平多",
    "open short": "开空",
    "close short": "平空",
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


def format_order_status(status: Any, lang_code: str = "zh") -> str:
    """Human-readable order status in the target language.

    Hyperliquid returns raw values like ``open`` / ``filled`` / ``canceled``;
    in Chinese these are translated (with the original kept in parentheses).
    """
    if _lang_code(lang_code) == "zh":
        key = str(status).strip().lower() if status else "unknown"
        return ORDER_STATUS_LABELS_ZH.get(key, str(status) if status else "未知")
    return str(status) if status else "Unknown"


def format_order_type(value: Any, lang_code: str = "zh") -> str:
    """Human-readable order type / time-in-force in the target language.

    Hyperliquid frontend order data exposes values such as ``Limit`` and
    ``Stop Market`` via ``orderType``.
    """
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
    if key == "B":
        return "买入 / 做多" if _lang_code(lang_code) == "zh" else "Buy"
    if key == "A":
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

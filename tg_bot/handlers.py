import logging
import json
import re
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import uuid
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from core.config import settings
from infrastructure.db import add_address, get_addresses_with_notes, remove_address, get_setting, set_setting, update_note, update_address_settings
from infrastructure.hl_client import HyperliquidClient
from tg_bot.locales import format_order_type, get_text

logger = logging.getLogger(__name__)
router = Router()

class NoteState(StatesGroup):
    waiting_for_note = State()


_hl_client: Optional[HyperliquidClient] = None
_monitor: Any = None  # services.monitor.BlockchainMonitor

# Ephemeral per-session cache: maps short uuid -> dict with context (address, page, query).
_context_cache: Dict[str, Dict[str, Any]] = {}

_EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def set_hl_client(client: HyperliquidClient) -> None:
    """Inject the shared HyperliquidClient instance."""
    global _hl_client
    _hl_client = client


def set_monitor(monitor: Any) -> None:
    """Inject the BlockchainMonitor instance."""
    global _monitor
    _monitor = monitor


def _get_hl_client() -> HyperliquidClient:
    if _hl_client is None:
        raise RuntimeError(
            "HyperliquidClient not injected. Call set_hl_client() first."
        )
    return _hl_client


def is_valid_evm_address(address: str) -> bool:
    return bool(_EVM_ADDRESS_RE.match(address))


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert *value* to float, returning *default* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_user_lang(event: Union[Message, CallbackQuery]) -> str:
    """Determine the UI language from the event sender.

    Recognises ``zh`` variants; everything else falls back to the configured
    ``BOT_LANGUAGE`` default.
    """
    lang = getattr(event.from_user, "language_code", None) if event.from_user else None
    if lang and "zh" in lang.lower():
        return "zh"
    if lang and lang.lower().startswith("en"):
        return "en"
    return settings.BOT_LANGUAGE


def admin_only(func: Callable) -> Callable:
    """Decorator to enforce admin-only access.

    Safely handles events without a ``from_user`` (e.g. channel posts).
    """

    @wraps(func)
    async def wrapper(
        event: Union[Message, CallbackQuery], *args: Any, **kwargs: Any
    ) -> Any:
        # Anonymous events (channel forwards, etc.) have no from_user.
        if event.from_user is None:
            logger.warning("Ignored event with no from_user identity.")
            return

        if isinstance(event, Message):
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery) and event.message:
            chat_id = event.message.chat.id
        else:
            logger.warning("Cannot determine chat_id for event; denying access.")
            return

        if chat_id != settings.TG_ADMIN_CHAT_ID:
            logger.warning(
                "Unauthorized access attempt from user %d in chat %d",
                event.from_user.id,
                chat_id,
            )
            if isinstance(event, CallbackQuery):
                await event.answer("Unauthorized", show_alert=True)
            return
        return await func(event, *args, **kwargs)

    return wrapper


def _visual_len(text: str) -> int:
    return sum(2 if ord(c) > 127 else 1 for c in text)

def _build_paginated_keyboard(
    addresses_with_notes: List[tuple[str, str]], 
    page: int = 0, 
    query: str = ""
) -> InlineKeyboardMarkup:
    if query:
        q = query.lower()
        filtered = []
        for addr, note in addresses_with_notes:
            if q in addr.lower() or (note and q in note.lower()):
                filtered.append((addr, note))
    else:
        filtered = addresses_with_notes
        
    ITEMS_PER_PAGE = 10
    total_pages = max(1, (len(filtered) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_items = filtered[start_idx:end_idx]
    
    keyboard: List[List[InlineKeyboardButton]] = []
    
    for addr, note in page_items:
        cache_key = uuid.uuid4().hex[:8]
        _context_cache[cache_key] = {"address": addr, "note": note, "page": page, "query": query}
        
        if note:
            # Full label visual length: visual_len(note) + 3 (" ()") + 42 (address)
            if _visual_len(addr) + 3 + _visual_len(note) > 60:
                # Shorten address to make room for the note
                short_addr = f"{addr[:6]}...{addr[-4:]}"
                label = f"{note} ({short_addr})"
                if _visual_len(label) > 60:
                    # ' (0x1234...abcd)' is 16 visual width.
                    # Max note visual width = 60 - 16 - 3(for ...) = 41
                    max_note_width = 41
                    current_len = 0
                    trunc_idx = 0
                    for i, c in enumerate(note):
                        current_len += 2 if ord(c) > 127 else 1
                        if current_len > max_note_width:
                            trunc_idx = i
                            break
                    trunc_note = note[:trunc_idx] + "..."
                    label = f"{trunc_note} ({short_addr})"
            else:
                label = f"{note} ({addr})"
        else:
            label = addr
            
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"info:{cache_key}")])
        
    nav_row = []
    if page > 0:
        prev_key = uuid.uuid4().hex[:8]
        _context_cache[prev_key] = {"page": page - 1, "query": query}
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"list_page:{prev_key}"))
        
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
        
    if page < total_pages - 1:
        next_key = uuid.uuid4().hex[:8]
        _context_cache[next_key] = {"page": page + 1, "query": query}
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"list_page:{next_key}"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def _build_action_keyboard(cache_key: str, lang: str, current_view: str) -> InlineKeyboardMarkup:
    buttons = []
    if current_view != "info":
        buttons.append(InlineKeyboardButton(text=get_text(lang, "btn_info"), callback_data=f"info:{cache_key}"))
    if current_view != "stats":
        buttons.append(InlineKeyboardButton(text=get_text(lang, "btn_stats"), callback_data=f"stats:{cache_key}"))
    if current_view != "orders":
        buttons.append(InlineKeyboardButton(text=get_text(lang, "btn_orders"), callback_data=f"orders:{cache_key}"))
        
    if current_view != "settings":
        buttons.append(InlineKeyboardButton(text=get_text(lang, "btn_settings"), callback_data=f"userset:{cache_key}"))
    buttons.append(InlineKeyboardButton(text=get_text(lang, "btn_note"), callback_data=f"setnote:{cache_key}"))
    buttons.append(InlineKeyboardButton(text=get_text(lang, "btn_delete"), callback_data=f"deladdr:{cache_key}"))
    buttons.append(InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data=f"list_page:{cache_key}"))
    
    keyboard = []
    keyboard.append(buttons[:-3])
    keyboard.append(buttons[-3:])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _resolve_callback_address(data: str) -> Optional[str]:
    parts = data.split(":", 1)
    if len(parts) != 2:
        return None
    key = parts[1]

    ctx = _context_cache.get(key)
    if ctx and "address" in ctx:
        address = ctx["address"]
        if is_valid_evm_address(address):
            return address

    if is_valid_evm_address(key):
        return key

    return None


@router.message(Command("start", "help"))
@admin_only
async def cmd_start(message: Message) -> None:
    lang = get_user_lang(message)
    try:
        await message.answer(get_text(lang, "welcome"), parse_mode="HTML")
    except Exception:
        logger.error("Failed to send /start response.", exc_info=True)


import re
@router.message(Command("add"))
@admin_only
async def cmd_add(message: Message) -> None:
    lang = get_user_lang(message)
    msg_text = message.text if message.text else ""
    
    address_pattern = r"0x[a-fA-F0-9]{40}"
    addresses = re.findall(address_pattern, msg_text)
    
    if not addresses:
        await message.answer(get_text(lang, "usage_add"))
        return
        
    parts = re.split(address_pattern, msg_text)
    notes = []
    for i in range(1, len(parts)):
        note = parts[i].strip(" ,\n\r\t-")
        notes.append(note if note else None)
        
    if len(addresses) > 1 and all(n is None for n in notes[:-1]) and notes[-1] is not None:
        unified_note = notes[-1]
        notes = [unified_note] * len(addresses)

    try:
        added_count = 0
        for addr, note in zip(addresses, notes):
            success = await add_address(addr, note)
            if success:
                added_count += 1
                if _monitor:
                    await _monitor.subscribe(addr)
                logger.info("Added address: %s with note: %s", addr, note)
        
        if added_count == 1 and len(addresses) == 1:
            await message.answer(get_text(lang, "add_success", address=addresses[0]), parse_mode="HTML")
        elif added_count > 0:
            await message.answer(get_text(lang, "batch_add_success", count=added_count))
        else:
            await message.answer(get_text(lang, "add_exists"))
    except Exception:
        logger.error("Error in /add handler.", exc_info=True)


@router.message(Command("del"))
@admin_only
async def cmd_del(message: Message) -> None:
    lang = get_user_lang(message)
    text = message.text if message.text else ""
    addresses = re.findall(r"0x[a-fA-F0-9]{40}", text)
    
    if not addresses:
        await message.answer(get_text(lang, "usage_del"))
        return

    try:
        removed_count = 0
        for addr in addresses:
            success = await remove_address(addr)
            if success:
                removed_count += 1
                if _monitor:
                    await _monitor.unsubscribe(addr)
                logger.info("Removed address: %s", addr)
        
        if removed_count == 1 and len(addresses) == 1:
            await message.answer(get_text(lang, "del_success", address=addresses[0]), parse_mode="HTML")
        elif removed_count > 0:
            await message.answer(get_text(lang, "batch_del_success", count=removed_count))
        else:
            await message.answer(get_text(lang, "del_not_found"))
    except Exception:
        logger.error("Error in /del handler.", exc_info=True)


@router.message(Command("list", "info", "orders"))
@admin_only
async def cmd_list(message: Message) -> None:
    lang = get_user_lang(message)
    args = message.text.split(maxsplit=1) if message.text else []
    
    query = ""
    page = 0
    if len(args) > 1:
        arg = args[1].strip()
        if arg.isdigit():
            page = max(0, int(arg) - 1)
        else:
            query = arg

    try:
        addresses_with_notes = await get_addresses_with_notes()
        if not addresses_with_notes:
            await message.answer(get_text(lang, "list_empty"))
            return
            
        await message.answer(
            get_text(lang, "select_address"),
            reply_markup=_build_paginated_keyboard(addresses_with_notes, page, query),
        )
    except Exception:
        logger.error("Error in /list handler.", exc_info=True)








@router.message(Command("set_filter"))
@admin_only
async def cmd_set_filter(message: Message) -> None:
    lang = get_user_lang(message)
    args = message.text.split() if message.text else []
    
    if len(args) == 1:
        current = await get_setting("min_notional_threshold", "0")
        await message.answer(get_text(lang, "filter_current", amount=current))
        return
        
    if len(args) != 2:
        await message.answer(get_text(lang, "filter_usage"))
        return
        
    try:
        val = float(args[1])
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer(get_text(lang, "filter_invalid"))
        return
        
    try:
        if val == 0:
            await set_setting("min_notional_threshold", "0")
            await message.answer(get_text(lang, "filter_cleared"))
        else:
            await set_setting("min_notional_threshold", str(val))
            await message.answer(get_text(lang, "filter_set", amount=f"{val:,.2f}"))
            
        if _monitor:
            _monitor.min_notional_threshold = val
    except Exception:
        logger.error("Error setting filter.", exc_info=True)


def _build_global_settings_keyboard(lang: str, settings_dict: dict) -> InlineKeyboardMarkup:
    types = ["fills", "orders", "events", "fundings", "ledger"]
    keyboard = []
    for t in types:
        is_on = settings_dict.get(f"notify_{t}", True)
        state_str = get_text(lang, "state_on") if is_on else get_text(lang, "state_off")
        btn = InlineKeyboardButton(
            text=f"{get_text(lang, f'type_{t}')}: {state_str}",
            callback_data=f"gset:{t}:{int(not is_on)}"
        )
        keyboard.append([btn])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def _build_user_settings_keyboard(lang: str, cache_key: str, settings_dict: dict) -> InlineKeyboardMarkup:
    types = ["fills", "orders", "events", "fundings", "ledger"]
    keyboard = []
    for t in types:
        pref = settings_dict.get(f"notify_{t}")
        if pref == "1":
            state_str = get_text(lang, "state_on")
            next_val = "0"
        elif pref == "0":
            state_str = get_text(lang, "state_off")
            next_val = "global"
        else:
            state_str = get_text(lang, "state_global")
            next_val = "1"
            
        btn = InlineKeyboardButton(
            text=f"{get_text(lang, f'type_{t}')}: {state_str}",
            callback_data=f"uset:{t}:{next_val}:{cache_key}"
        )
        keyboard.append([btn])
    
    keyboard.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data=f"info:{cache_key}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(Command("settings"))
@admin_only
async def cmd_settings(message: Message) -> None:
    lang = get_user_lang(message)
    if _monitor:
        settings_dict = _monitor._global_settings
    else:
        settings_dict = {}
    
    await message.answer(
        get_text(lang, "settings_global_title"),
        reply_markup=_build_global_settings_keyboard(lang, settings_dict),
        parse_mode="HTML"
    )

@router.callback_query(lambda c: c.data and c.data.startswith("gset:"))
@admin_only
async def process_gset_callback(callback_query: CallbackQuery) -> None:
    lang = get_user_lang(callback_query)
    parts = callback_query.data.split(":")
    if len(parts) == 3:
        notify_type = parts[1]
        val = parts[2]
        enabled = val == "1"
        await set_setting(f"global_notify_{notify_type}", val)
        if _monitor:
            _monitor.set_global_setting(notify_type, enabled)
            
        await callback_query.message.edit_reply_markup(
            reply_markup=_build_global_settings_keyboard(lang, _monitor._global_settings if _monitor else {})
        )
    await callback_query.answer()
    
@router.callback_query(lambda c: c.data and c.data.startswith("userset:"))
@admin_only
async def process_userset_callback(callback_query: CallbackQuery) -> None:
    lang = get_user_lang(callback_query)
    parts = callback_query.data.split(":", 1)
    if len(parts) < 2: return
    
    cache_key = parts[1]
    ctx = _context_cache.get(cache_key)
    if not ctx or "address" not in ctx:
        await callback_query.answer(get_text(lang, "invalid_address"), show_alert=True)
        return
        
    address = ctx["address"]
    addr_settings = _monitor._monitored_addresses.get(address, {}) if _monitor else {}
    
    msg = get_text(lang, "settings_user_title", address=address)
    markup = _build_user_settings_keyboard(lang, cache_key, addr_settings)
    await callback_query.message.edit_text(msg, reply_markup=markup, parse_mode="HTML")
    await callback_query.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("uset:"))
@admin_only
async def process_uset_callback(callback_query: CallbackQuery) -> None:
    lang = get_user_lang(callback_query)
    parts = callback_query.data.split(":")
    if len(parts) == 4:
        notify_type = parts[1]
        val = parts[2]
        cache_key = parts[3]
        
        ctx = _context_cache.get(cache_key)
        if ctx and "address" in ctx:
            address = ctx["address"]
            if _monitor:
                _monitor.set_address_setting(address, notify_type, val)
                await update_address_settings(address, _monitor._monitored_addresses.get(address, {}))
                addr_settings = _monitor._monitored_addresses.get(address, {})
                markup = _build_user_settings_keyboard(lang, cache_key, addr_settings)
                await callback_query.message.edit_reply_markup(reply_markup=markup)
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("info:"))
@admin_only
async def process_info_callback(callback_query: CallbackQuery) -> None:
    lang = get_user_lang(callback_query)

    address = _resolve_callback_address(callback_query.data)  # type: ignore[arg-type]
    if not address:
        await callback_query.answer(get_text(lang, "invalid_address"), show_alert=True)
        return

    cache_key = callback_query.data.split(":", 1)[1] if ":" in callback_query.data else ""
    ctx = _context_cache.get(cache_key, {})
    note = ctx.get("note")
    address_display = f"{note} (<code>{address}</code>)" if note else f"<code>{address}</code>"

    hl = _get_hl_client()

    try:
        state = await hl.get_clearinghouse_state(address)
        margin = state.get("marginSummary", {})
        equity = _safe_float(margin.get("accountValue", "0"))
        margin_used = _safe_float(margin.get("totalMarginUsed", "0"))
        raw_usd = _safe_float(margin.get("totalRawUsd", "0"))
        total_ntl = _safe_float(margin.get("totalNtlPos", "0"))
        
        withdrawable = _safe_float(state.get("withdrawable", "0"))
        cross_maint = _safe_float(state.get("crossMaintenanceMarginUsed", "0"))

        positions = state.get("assetPositions", [])

        positions_str = ""
        total_upnl = 0.0

        for p in positions:
            pos = p.get("position", {})
            coin = pos.get("coin", "")
            szi = _safe_float(pos.get("szi", "0"))

            if szi == 0:
                continue

            entry_px = _safe_float(pos.get("entryPx", "0"))
            unrealized_pnl = _safe_float(pos.get("unrealizedPnl", "0"))
            total_upnl += unrealized_pnl
            
            position_value = _safe_float(pos.get("positionValue", "0"))
            roe = _safe_float(pos.get("returnOnEquity", "0"))
            liquidation_px = _safe_float(pos.get("liquidationPx", "0"))
            
            leverage = pos.get("leverage", {})
            lev_val = leverage.get("value", 0)
            lev_type = leverage.get("type", "cross")
            
            max_leverage = pos.get("maxLeverage", 0)
            
            cum_funding = pos.get("cumFunding", {})
            funding_all = _safe_float(cum_funding.get("allTime", "0"))

            pos_dir = get_text(lang, "pos_long") if szi > 0 else get_text(lang, "pos_short")
            lev_dir = get_text(lang, "lev_cross") if lev_type == "cross" else get_text(lang, "lev_isolated")

            positions_str += get_text(
                lang,
                "position_detail",
                coin=coin,
                pos_dir=pos_dir,
                szi=abs(szi),
                lev_val=lev_val,
                lev_dir=lev_dir,
                max_leverage=max_leverage,
                entry_px=entry_px,
                liquidation_px=liquidation_px,
                position_value=position_value,
                unrealized_pnl=unrealized_pnl,
                roe=roe,
                funding_all=funding_all,
            )

        if not positions_str:
            positions_str = get_text(lang, "no_positions")

        text = get_text(
            lang,
            "info_result",
            address_display=address_display,
            equity=f"{equity:,.2f}",
            raw_usd=f"{raw_usd:,.2f}",
            withdrawable=f"{withdrawable:,.2f}",
            total_ntl=f"{total_ntl:,.2f}",
            margin_used=f"{margin_used:,.2f}",
            cross_maint=f"{cross_maint:,.2f}",
            upnl=f"{total_upnl:,.2f}",
            positions=positions_str,
        )

        MAX_LEN = 4000
        cache_key = callback_query.data.split(":", 1)[1] if callback_query.data and ":" in callback_query.data else ""
        markup = _build_action_keyboard(cache_key, lang, "info") if cache_key else None
        
        if len(text) <= MAX_LEN:
            if callback_query.message:
                await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            else:
                await callback_query.answer(get_text(lang, "fetch_failed"), show_alert=True)
        else:
            parts = text.split("\n\n")
            chunks = []
            current_chunk = ""
            for part in parts:
                if len(current_chunk) + len(part) + 2 > MAX_LEN:
                    chunks.append(current_chunk)
                    current_chunk = part
                else:
                    current_chunk += ("\n\n" + part) if current_chunk else part
            if current_chunk:
                chunks.append(current_chunk)
            
            if callback_query.message:
                await callback_query.message.edit_text(chunks[0], parse_mode="HTML")
                for i, chunk in enumerate(chunks[1:]):
                    if i == len(chunks) - 2:  # Last chunk
                        await callback_query.message.answer(chunk, parse_mode="HTML", reply_markup=markup)
                    else:
                        await callback_query.message.answer(chunk, parse_mode="HTML", reply_markup=markup if chunk == chunks[-1] else None)
            else:
                await callback_query.answer(get_text(lang, "fetch_failed"), show_alert=True)
    except Exception as e:
        logger.error("Error fetching info for %s: %s", address, e)
        await callback_query.answer(get_text(lang, "fetch_failed"), show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("orders:"))
@admin_only
async def process_orders_callback(callback_query: CallbackQuery) -> None:
    lang = get_user_lang(callback_query)

    address = _resolve_callback_address(callback_query.data)  # type: ignore[arg-type]
    if not address:
        await callback_query.answer(get_text(lang, "invalid_address"), show_alert=True)
        return

    cache_key = callback_query.data.split(":", 1)[1] if ":" in callback_query.data else ""
    ctx = _context_cache.get(cache_key, {})
    note = ctx.get("note")
    address_display = f"{note} (<code>{address}</code>)" if note else f"<code>{address}</code>"

    hl = _get_hl_client()

    try:
        orders = await hl.get_open_orders(address)
        if _monitor:
            _monitor.register_order_owners(address, orders)
        orders.sort(key=lambda x: x.get("coin", ""))
        
        orders_str = ""
        from datetime import datetime
        for o in orders:
            coin = o.get("coin", "")
            side = o.get("side", "")
            if side == "B":
                dir_str = get_text(lang, "pos_long") if lang == "zh" else "Buy"
            else:
                dir_str = get_text(lang, "pos_short") if lang == "zh" else "Sell"
                
            limit_px = _safe_float(o.get("limitPx", "0"))
            sz = _safe_float(o.get("sz", "0"))
            orig_sz = _safe_float(o.get("origSz", "0"))
            oid = o.get("oid", "")
            reduce_only = "Yes" if o.get("reduceOnly") else "No"
            if lang == "zh":
                reduce_only = "是 (Yes)" if o.get("reduceOnly") else "否 (No)"
            post_only = "Yes" if o.get("postOnly") else "No"
            if lang == "zh":
                post_only = "是 (Yes)" if o.get("postOnly") else "否 (No)"
                
            order_type = format_order_type(o.get("orderType") or o.get("tif"), lang)
            ts = o.get("timestamp", 0)
            time_str = datetime.fromtimestamp(ts / 1000.0).strftime('%Y-%m-%d %H:%M:%S') if ts else "Unknown"

            orders_str += get_text(
                lang,
                "order_item",
                coin=coin,
                dir=dir_str,
                limit_px=f"{limit_px:,.4f}",
                sz=f"{sz:,.4f}",
                orig_sz=f"{orig_sz:,.4f}",
                oid=oid,
                reduce_only=reduce_only,
                post_only=post_only,
                order_type=order_type,
                time=time_str
            )

        if not orders_str:
            orders_str = get_text(lang, "no_orders")

        text = get_text(lang, "orders_result", address_display=address_display, orders=orders_str)

        MAX_LEN = 4000
        if len(text) <= MAX_LEN:
            markup = _build_action_keyboard(callback_query.data.split(":", 1)[1], lang, "orders")
            if callback_query.message:
                await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            else:
                await callback_query.answer(get_text(lang, "fetch_failed"), show_alert=True)
        else:
            parts = text.split("\n\n")
            chunks = []
            current_chunk = ""
            for part in parts:
                if len(current_chunk) + len(part) + 2 > MAX_LEN:
                    chunks.append(current_chunk)
                    current_chunk = part
                else:
                    current_chunk += ("\n\n" + part) if current_chunk else part
            if current_chunk:
                chunks.append(current_chunk)
            
            if callback_query.message:
                await callback_query.message.edit_text(chunks[0], parse_mode="HTML")
                for chunk in chunks[1:]:
                    await callback_query.message.answer(chunk, parse_mode="HTML", reply_markup=markup if chunk == chunks[-1] else None)
            else:
                await callback_query.answer(get_text(lang, "fetch_failed"), show_alert=True)
    except Exception as e:
        logger.error("Error fetching orders for %s: %s", address, e)
        await callback_query.answer(get_text(lang, "fetch_failed"), show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("stats:"))
@admin_only
async def process_stats_callback(callback_query: CallbackQuery) -> None:
    lang = get_user_lang(callback_query)

    address = _resolve_callback_address(callback_query.data)  # type: ignore[arg-type]
    if not address:
        await callback_query.answer(get_text(lang, "invalid_address"), show_alert=True)
        return

    cache_key = callback_query.data.split(":", 1)[1] if ":" in callback_query.data else ""
    ctx = _context_cache.get(cache_key, {})
    note = ctx.get("note")
    address_display = f"{note} (<code>{address}</code>)" if note else f"<code>{address}</code>"

    hl = _get_hl_client()

    try:
        portfolio_data = await hl.get_portfolio(address)
        stats_str = ""
        
        periods_to_show = ["day", "week", "month", "allTime"]
        
        for item in portfolio_data:
            if not isinstance(item, list) or len(item) != 2:
                continue
            period, p_data = item[0], item[1]
            
            if period not in periods_to_show:
                continue
                
            period_label = period
            if period == "day": period_label = "24h" if lang == "en" else "24小时"
            elif period == "week": period_label = "7d" if lang == "en" else "近 7 天"
            elif period == "month": period_label = "30d" if lang == "en" else "近 30 天"
            elif period == "allTime": period_label = "All Time" if lang == "en" else "全部"
            
            pnl_history = p_data.get("pnlHistory", [])
            acc_history = p_data.get("accountValueHistory", [])
            
            pnl = 0.0
            if pnl_history and len(pnl_history) >= 2:
                first_pnl = _safe_float(pnl_history[0][1])
                last_pnl = _safe_float(pnl_history[-1][1])
                pnl = last_pnl - first_pnl
                
            roi = 0.0
            if acc_history and len(acc_history) >= 1:
                start_acc_val = _safe_float(acc_history[0][1])
                if start_acc_val > 0:
                    roi = pnl / start_acc_val
                    
            vol = _safe_float(p_data.get("vlm", "0"))
            
            pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"
            roi_str = f"+{roi:.2%}" if roi >= 0 else f"{roi:.2%}"
            
            if vol >= 1_000_000:
                vol_str = f"${vol/1_000_000:.2f}M"
            elif vol >= 1_000:
                vol_str = f"${vol/1_000:.2f}K"
            else:
                vol_str = f"${vol:,.2f}"
                
            stats_str += get_text(
                lang,
                "stats_item",
                period=period_label,
                pnl=pnl_str,
                roi=roi_str,
                vol=vol_str
            )
            
        if not stats_str:
            stats_str = get_text(lang, "fetch_failed")

        text = get_text(lang, "stats_result", address_display=address_display, stats=stats_str)
        
        markup = _build_action_keyboard(callback_query.data.split(":", 1)[1], lang, "stats")
        if callback_query.message:
            await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            await callback_query.answer(get_text(lang, "fetch_failed"), show_alert=True)
            
        await callback_query.answer()
        
    except Exception as e:
        logger.error("Error fetching stats for %s: %s", address, e)
        await callback_query.answer(get_text(lang, "fetch_failed"), show_alert=True)

@router.callback_query(lambda c: c.data == "ignore")
async def process_ignore(callback_query: CallbackQuery) -> None:
    await callback_query.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("list_page:"))
@admin_only
async def process_list_page(callback_query: CallbackQuery) -> None:
    lang = get_user_lang(callback_query)
    parts = callback_query.data.split(":", 1)
    if len(parts) < 2: return
    
    cache_key = parts[1]
    ctx = _context_cache.get(cache_key)
    if not ctx:
        await callback_query.answer(get_text(lang, "fetch_failed"), show_alert=True)
        return
        
    page = ctx.get("page", 0)
    query = ctx.get("query", "")
    
    try:
        addresses_with_notes = await get_addresses_with_notes()
        if not addresses_with_notes:
            await callback_query.message.edit_text(get_text(lang, "list_empty"))
            return
            
        await callback_query.message.edit_text(
            get_text(lang, "select_address"),
            reply_markup=_build_paginated_keyboard(addresses_with_notes, page, query),
        )
    except Exception:
        logger.error("Error in list_page handler.", exc_info=True)

@router.callback_query(lambda c: c.data and c.data.startswith("setnote:"))
@admin_only
async def process_setnote_callback(callback_query: CallbackQuery, state: FSMContext) -> None:
    lang = get_user_lang(callback_query)
    parts = callback_query.data.split(":", 1)
    if len(parts) < 2: return
    
    cache_key = parts[1]
    ctx = _context_cache.get(cache_key)
    if not ctx or "address" not in ctx:
        await callback_query.answer(get_text(lang, "invalid_address"), show_alert=True)
        return
        
    address = ctx["address"]
    await state.set_state(NoteState.waiting_for_note)
    await state.update_data(address=address, cache_key=cache_key)
    
    msg = get_text(lang, "set_note_prompt", address=address)
    await callback_query.message.answer(msg, parse_mode="HTML")
    await callback_query.answer()

@router.message(NoteState.waiting_for_note)
@admin_only
async def process_note_input(message: Message, state: FSMContext) -> None:
    lang = get_user_lang(message)
    data = await state.get_data()
    address = data.get("address")
    cache_key = data.get("cache_key")
    
    text = message.text.strip() if message.text else ""
    
    if text == "/cancel":
        await state.clear()
        await message.answer(get_text(lang, "set_note_cancelled"))
        return
        
    if text == "-":
        await update_note(address, None)
        await message.answer(get_text(lang, "set_note_cleared", address=address), parse_mode="HTML")
    else:
        await update_note(address, text)
        await message.answer(get_text(lang, "set_note_success", address=address), parse_mode="HTML")
        
    await state.clear()
    
    ctx = _context_cache.get(cache_key, {})
    page = ctx.get("page", 0)
    query = ctx.get("query", "")
    try:
        addresses_with_notes = await get_addresses_with_notes()
        await message.answer(
            get_text(lang, "select_address"),
            reply_markup=_build_paginated_keyboard(addresses_with_notes, page, query),
        )
    except Exception:
        pass

@router.callback_query(lambda c: c.data and c.data.startswith("deladdr:"))
@admin_only
async def process_deladdr_callback(callback_query: CallbackQuery) -> None:
    lang = get_user_lang(callback_query)
    address = _resolve_callback_address(callback_query.data)
    if not address:
        return
        
    try:
        success = await remove_address(address)
        if success and _monitor:
            await _monitor.unsubscribe(address)
            
        await callback_query.answer(get_text(lang, "delete_success", address=address))
        
        cache_key = callback_query.data.split(":", 1)[1] if ":" in callback_query.data else ""
        ctx = _context_cache.get(cache_key, {})
        page = ctx.get("page", 0)
        query = ctx.get("query", "")
        
        addresses_with_notes = await get_addresses_with_notes()
        if not addresses_with_notes:
            await callback_query.message.edit_text(get_text(lang, "list_empty"))
            return
            
        await callback_query.message.edit_text(
            get_text(lang, "select_address"),
            reply_markup=_build_paginated_keyboard(addresses_with_notes, page, query),
        )
    except Exception:
        logger.error("Error in deladdr callback", exc_info=True)

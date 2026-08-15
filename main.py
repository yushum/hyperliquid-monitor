import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from core.config import settings
from infrastructure.db import close_db, init_db
from infrastructure.hl_client import HyperliquidClient
from services.monitor import BlockchainMonitor
from services.notifier import TelegramNotifier
from tg_bot.handlers import router, set_hl_client, set_monitor

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    hl_client: HyperliquidClient | None = None
    bot: Bot | None = None
    monitor: BlockchainMonitor | None = None
    try:
        await init_db()

        hl_client = HyperliquidClient()
        await hl_client.start()
        bot = Bot(token=settings.TG_BOT_TOKEN.get_secret_value())

        if settings.BOT_LANGUAGE == "zh":
            descriptions = {
                "start": "启动机器人",
                "help": "查看帮助",
                "add": "添加监控地址",
                "del": "移除监控地址",
                "list": "查看和管理地址",
                "settings": "全局通知设置",
                "set_filter": "设置通知金额阈值",
            }
        else:
            descriptions = {
                "start": "Start the bot",
                "help": "Show help",
                "add": "Add an address",
                "del": "Remove an address",
                "list": "Manage addresses",
                "settings": "Global notification settings",
                "set_filter": "Set notification threshold",
            }
        await bot.set_my_commands(
            [
                BotCommand(command=name, description=description)
                for name, description in descriptions.items()
            ]
        )

        dp = Dispatcher()
        dp.include_router(router)
        notifier = TelegramNotifier(bot, settings.TG_ADMIN_CHAT_ID)
        monitor = BlockchainMonitor(notifier, hl_client=hl_client)
        await monitor.start()
        set_hl_client(hl_client)
        set_monitor(monitor)

        logger.info("Bot is starting...")
        await dp.start_polling(bot)
    finally:
        if monitor is not None:
            await _safe_cleanup("monitor", monitor.stop)
        if hl_client is not None:
            await _safe_cleanup("hl_client", hl_client.close)
        await _safe_cleanup("database", close_db)
        if bot is not None:
            await _safe_cleanup("bot_session", bot.session.close)
        logger.info("All resources released. Goodbye.")


async def _safe_cleanup(name: str, coro_fn: Any) -> None:
    """Run a cleanup coroutine, logging but not propagating errors.

    This prevents one failing cleanup step from blocking subsequent ones.
    """
    try:
        await coro_fn()
    except Exception:
        logger.exception("Error during %s cleanup.", name)


if __name__ == "__main__":
    asyncio.run(main())

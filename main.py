import asyncio
import logging
import signal
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
    await init_db()

    hl_client = HyperliquidClient()
    await hl_client.start()

    bot = Bot(token=settings.TG_BOT_TOKEN.get_secret_value())

    commands = [
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="help", description="Show help"),
        BotCommand(command="add", description="Add an address"),
        BotCommand(command="del", description="Remove an address"),
        BotCommand(command="list", description="Manage addresses"),
        BotCommand(command="settings", description="Global notification settings"),
        BotCommand(command="set_filter", description="Set notification threshold"),
    ]
    await bot.set_my_commands(commands)

    dp = Dispatcher()
    dp.include_router(router)

    notifier = TelegramNotifier(bot, settings.TG_ADMIN_CHAT_ID)
    monitor = BlockchainMonitor(notifier)
    await monitor.start()

    set_hl_client(hl_client)
    set_monitor(monitor)

    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Received shutdown signal.")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    logger.info("Bot is starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await _safe_cleanup("monitor", monitor.stop)
        await _safe_cleanup("hl_client", hl_client.close)
        await _safe_cleanup("database", close_db)
        await _safe_cleanup("bot_session", bot.session.close)
        logger.info("All resources released. Goodbye.")


async def _safe_cleanup(name: str, coro_fn: Any) -> None:
    """Run a cleanup coroutine, logging but not propagating errors.

    This prevents one failing cleanup step from blocking subsequent ones.
    """
    try:
        await coro_fn()
    except Exception:
        logger.error("Error during %s cleanup.", name, exc_info=True)




if __name__ == "__main__":
    asyncio.run(main())

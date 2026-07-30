import asyncio
import logging
import json
from typing import List, Optional, Dict

import aiosqlite

from core.config import settings

logger = logging.getLogger(__name__)

# Module-level shared connection, protected by an asyncio lock.
_db: Optional[aiosqlite.Connection] = None
_db_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    """Return the shared database connection, creating it on first call.

    Uses an asyncio.Lock to prevent the race condition where two coroutines
    both see ``_db is None`` and open duplicate connections.
    """
    global _db
    if _db is not None:
        return _db
    async with _db_lock:
        # Double-check after acquiring the lock.
        if _db is None:
            _db = await aiosqlite.connect(settings.DB_PATH)
            _db.row_factory = aiosqlite.Row
            await _db.execute("PRAGMA journal_mode=WAL;")
            logger.info("Database connection opened with WAL mode.")
    return _db


async def close_db() -> None:
    """Close the shared database connection. Call once at shutdown."""
    global _db
    async with _db_lock:
        if _db is not None:
            try:
                await _db.close()
            except Exception:
                logger.warning("Error closing database connection.", exc_info=True)
            finally:
                _db = None
                logger.info("Database connection closed.")


async def init_db() -> None:
    """Create tables and run migrations."""
    db = await get_db()
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitored_addresses (
                address TEXT PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_fill_time INTEGER DEFAULT 0
            )
        """)

        try:
            await db.execute(
                "ALTER TABLE monitored_addresses ADD COLUMN last_fill_time INTEGER DEFAULT 0"
            )
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute(
                "ALTER TABLE monitored_addresses ADD COLUMN note TEXT"
            )
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute(
                "ALTER TABLE monitored_addresses ADD COLUMN settings TEXT DEFAULT '{}'"
            )
        except aiosqlite.OperationalError:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.commit()
        logger.info("Database initialized.")
    except Exception:
        logger.error("Failed to initialize database.", exc_info=True)
        raise


async def add_address(address: str, note: Optional[str] = None) -> bool:
    """Add an address to monitoring. Returns False if already exists."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO monitored_addresses (address, note) VALUES (?, ?)",
            (address, note),
        )
        await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False
    except Exception:
        logger.error("Failed to add address %s.", address, exc_info=True)
        return False


async def remove_address(address: str) -> bool:
    """Remove an address from monitoring. Returns False if not found."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM monitored_addresses WHERE address = ?",
            (address,),
        )
        await db.commit()
        return cursor.rowcount > 0
    except Exception:
        logger.error("Failed to remove address %s.", address, exc_info=True)
        return False


async def get_all_addresses() -> List[str]:
    """Return all monitored addresses."""
    db = await get_db()
    try:
        async with db.execute("SELECT address FROM monitored_addresses") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    except Exception:
        logger.error("Failed to fetch addresses.", exc_info=True)
        return []


async def get_addresses_with_notes() -> List[tuple[str, Optional[str]]]:
    """Return all monitored addresses with their optional notes."""
    db = await get_db()
    try:
        async with db.execute("SELECT address, note FROM monitored_addresses") as cursor:
            rows = await cursor.fetchall()
            return [(row[0], row[1]) for row in rows]
    except Exception:
        logger.error("Failed to fetch addresses with notes.", exc_info=True)
        return []

async def get_all_address_settings() -> Dict[str, dict]:
    """Return all monitored addresses with their settings."""
    db = await get_db()
    try:
        async with db.execute("SELECT address, settings FROM monitored_addresses") as cursor:
            rows = await cursor.fetchall()
            res = {}
            for row in rows:
                addr = row[0]
                try:
                    res[addr] = json.loads(row[1]) if row[1] else {}
                except json.JSONDecodeError:
                    res[addr] = {}
            return res
    except Exception:
        logger.error("Failed to fetch address settings.", exc_info=True)
        return {}

async def update_address_settings(address: str, settings_dict: dict) -> bool:
    """Update the settings for a specific address."""
    db = await get_db()
    try:
        settings_str = json.dumps(settings_dict)
        cursor = await db.execute(
            "UPDATE monitored_addresses SET settings = ? WHERE address = ?",
            (settings_str, address),
        )
        await db.commit()
        return cursor.rowcount > 0
    except Exception:
        logger.error("Failed to update settings for %s.", address, exc_info=True)
        return False

async def update_note(address: str, note: Optional[str]) -> bool:
    """Update the note for a specific address. Returns True if successful."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE monitored_addresses SET note = ? WHERE address = ?",
            (note, address),
        )
        await db.commit()
        return cursor.rowcount > 0
    except Exception:
        logger.error("Failed to update note for %s.", address, exc_info=True)
        return False


async def get_last_fill_time(address: str) -> int:
    """Return the last fill timestamp for an address, or 0 if not found."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT last_fill_time FROM monitored_addresses WHERE address = ?",
            (address,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    except Exception:
        logger.error("Failed to get last fill time for %s.", address, exc_info=True)
        return 0


async def update_last_fill_time(address: str, fill_time: int) -> None:
    """Update the last fill timestamp for an address."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE monitored_addresses SET last_fill_time = ? WHERE address = ?",
            (fill_time, address),
        )
        await db.commit()
    except Exception:
        logger.error(
            "Failed to update last fill time for %s.", address, exc_info=True
        )

async def get_setting(key: str, default: str = "") -> str:
    """Get a global bot setting from the database."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT value FROM bot_settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default
    except Exception:
        logger.error("Failed to get setting for %s.", key, exc_info=True)
        return default


async def set_setting(key: str, value: str) -> None:
    """Set or update a global bot setting."""
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()
    except Exception:
        logger.error("Failed to set setting for %s.", key, exc_info=True)

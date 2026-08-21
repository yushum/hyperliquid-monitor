import asyncio
import json
import logging
import time

import aiosqlite

from core.config import settings

logger = logging.getLogger(__name__)

# Module-level shared connection, protected by an asyncio lock.
_db: aiosqlite.Connection | None = None
_db_lock = asyncio.Lock()
_db_write_lock = asyncio.Lock()


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

        async with db.execute("PRAGMA table_info(monitored_addresses)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}

        if "last_fill_time" not in columns:
            await db.execute(
                "ALTER TABLE monitored_addresses ADD COLUMN last_fill_time INTEGER DEFAULT 0"
            )
        if "note" not in columns:
            await db.execute("ALTER TABLE monitored_addresses ADD COLUMN note TEXT")
        if "settings" not in columns:
            await db.execute(
                "ALTER TABLE monitored_addresses ADD COLUMN settings TEXT DEFAULT '{}'"
            )
        if "last_order_time" not in columns:
            await db.execute(
                "ALTER TABLE monitored_addresses ADD COLUMN last_order_time INTEGER DEFAULT 0"
            )
        if "last_funding_time" not in columns:
            await db.execute(
                "ALTER TABLE monitored_addresses ADD COLUMN last_funding_time INTEGER DEFAULT 0"
            )
        if "last_ledger_time" not in columns:
            await db.execute(
                "ALTER TABLE monitored_addresses ADD COLUMN last_ledger_time INTEGER DEFAULT 0"
            )

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS processed_events (
                event_key TEXT PRIMARY KEY,
                event_time INTEGER NOT NULL DEFAULT 0,
                processed_at INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notification_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_key TEXT NOT NULL UNIQUE,
                address TEXT NOT NULL,
                notify_type TEXT NOT NULL,
                message TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at INTEGER NOT NULL,
                sent_at INTEGER,
                failed_at INTEGER
            )
        """)
        async with db.execute("PRAGMA table_info(notification_outbox)") as cursor:
            outbox_columns = {row[1] for row in await cursor.fetchall()}
        if "failed_at" not in outbox_columns:
            await db.execute(
                "ALTER TABLE notification_outbox ADD COLUMN failed_at INTEGER"
            )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outbox_due "
            "ON notification_outbox(sent_at, next_attempt_at, id)"
        )

        await db.commit()
        logger.info("Database initialized.")
    except Exception:
        logger.exception("Failed to initialize database.")
        raise


async def add_address(address: str, note: str | None = None) -> bool:
    """Add an address to monitoring. Returns False if already exists."""
    db = await get_db()
    address = address.lower()
    try:
        async with _db_write_lock:
            async with db.execute(
                "SELECT 1 FROM monitored_addresses WHERE address = ? COLLATE NOCASE",
                (address,),
            ) as cursor:
                if await cursor.fetchone():
                    return False
            await db.execute(
                "INSERT INTO monitored_addresses (address, note) VALUES (?, ?)",
                (address, note),
            )
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False
    except Exception:
        logger.exception("Failed to add address %s.", address)
        raise


async def remove_address(address: str) -> bool:
    """Remove an address from monitoring. Returns False if not found."""
    db = await get_db()
    try:
        async with _db_write_lock:
            cursor = await db.execute(
                "DELETE FROM monitored_addresses WHERE address = ? COLLATE NOCASE",
                (address.lower(),),
            )
            await db.commit()
        return cursor.rowcount > 0
    except Exception:
        logger.exception("Failed to remove address %s.", address)
        raise


async def get_all_addresses() -> list[str]:
    """Return all monitored addresses."""
    db = await get_db()
    try:
        async with db.execute("SELECT address FROM monitored_addresses") as cursor:
            rows = await cursor.fetchall()
            return [row[0].lower() for row in rows]
    except Exception:
        logger.exception("Failed to fetch addresses.")
        raise


async def get_addresses_with_notes() -> list[tuple[str, str | None]]:
    """Return all monitored addresses with their optional notes."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT address, note FROM monitored_addresses"
        ) as cursor:
            rows = await cursor.fetchall()
            return [(row[0].lower(), row[1]) for row in rows]
    except Exception:
        logger.exception("Failed to fetch addresses with notes.")
        raise


async def get_all_address_notes() -> dict[str, str | None]:
    """Return a mapping of address -> note for all monitored addresses."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT address, note FROM monitored_addresses"
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0].lower(): row[1] for row in rows}
    except Exception:
        logger.exception("Failed to fetch address notes.")
        raise


async def get_address_note(address: str) -> str | None:
    """Get the note for a specific address."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT note FROM monitored_addresses WHERE address = ? COLLATE NOCASE",
            (address.lower(),),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None
    except Exception:
        logger.exception("Failed to fetch note for %s.", address)
        raise


async def get_all_address_settings() -> dict[str, dict]:
    """Return all monitored addresses with their settings."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT address, settings FROM monitored_addresses ORDER BY added_at, address"
        ) as cursor:
            rows = await cursor.fetchall()
            res = {}
            for row in rows:
                addr = row[0].lower()
                try:
                    res[addr] = json.loads(row[1]) if row[1] else {}
                except json.JSONDecodeError:
                    res[addr] = {}
            return res
    except Exception:
        logger.exception("Failed to fetch address settings.")
        raise


async def update_address_settings(address: str, settings_dict: dict) -> bool:
    """Update the settings for a specific address."""
    db = await get_db()
    try:
        settings_str = json.dumps(settings_dict)
        async with _db_write_lock:
            cursor = await db.execute(
                "UPDATE monitored_addresses SET settings = ? WHERE address = ? COLLATE NOCASE",
                (settings_str, address.lower()),
            )
            await db.commit()
        return cursor.rowcount > 0
    except Exception:
        logger.exception("Failed to update settings for %s.", address)
        raise


async def update_note(address: str, note: str | None) -> bool:
    """Update the note for a specific address. Returns True if successful."""
    db = await get_db()
    try:
        async with _db_write_lock:
            cursor = await db.execute(
                "UPDATE monitored_addresses SET note = ? WHERE address = ? COLLATE NOCASE",
                (note, address.lower()),
            )
            await db.commit()
        return cursor.rowcount > 0
    except Exception:
        logger.exception("Failed to update note for %s.", address)
        raise


async def get_last_fill_time(address: str) -> int:
    """Return the last fill timestamp for an address, or 0 if not found."""
    db = await get_db()
    try:
        async with db.execute(
            "SELECT last_fill_time FROM monitored_addresses WHERE address = ? COLLATE NOCASE",
            (address.lower(),),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    except Exception:
        logger.exception("Failed to get last fill time for %s.", address)
        raise


async def update_last_fill_time(address: str, fill_time: int) -> None:
    """Update the last fill timestamp for an address."""
    db = await get_db()
    try:
        async with _db_write_lock:
            await db.execute(
                "UPDATE monitored_addresses "
                "SET last_fill_time = MAX(COALESCE(last_fill_time, 0), ?) "
                "WHERE address = ? COLLATE NOCASE",
                (fill_time, address.lower()),
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to update last fill time for %s.", address)
        raise


async def get_last_order_time(address: str) -> int:
    db = await get_db()
    async with db.execute(
        "SELECT last_order_time FROM monitored_addresses "
        "WHERE address = ? COLLATE NOCASE",
        (address.lower(),),
    ) as cursor:
        row = await cursor.fetchone()
        return int(row[0] or 0) if row else 0


async def update_last_order_time(address: str, order_time: int) -> None:
    db = await get_db()
    async with _db_write_lock:
        await db.execute(
            "UPDATE monitored_addresses "
            "SET last_order_time = MAX(COALESCE(last_order_time, 0), ?) "
            "WHERE address = ? COLLATE NOCASE",
            (int(order_time), address.lower()),
        )
        await db.commit()


async def _get_event_cursor(address: str, column: str) -> int:
    if column not in {"last_funding_time", "last_ledger_time"}:
        raise ValueError("unsupported event cursor")
    db = await get_db()
    async with db.execute(
        f"SELECT {column} FROM monitored_addresses "
        "WHERE address = ? COLLATE NOCASE",
        (address.lower(),),
    ) as cursor:
        row = await cursor.fetchone()
        return int(row[0] or 0) if row else 0


async def _update_event_cursor(address: str, column: str, event_time: int) -> None:
    if column not in {"last_funding_time", "last_ledger_time"}:
        raise ValueError("unsupported event cursor")
    db = await get_db()
    async with _db_write_lock:
        await db.execute(
            f"UPDATE monitored_addresses "
            f"SET {column} = MAX(COALESCE({column}, 0), ?) "
            "WHERE address = ? COLLATE NOCASE",
            (int(event_time), address.lower()),
        )
        await db.commit()


async def get_last_funding_time(address: str) -> int:
    return await _get_event_cursor(address, "last_funding_time")


async def update_last_funding_time(address: str, event_time: int) -> None:
    await _update_event_cursor(address, "last_funding_time", event_time)


async def get_last_ledger_time(address: str) -> int:
    return await _get_event_cursor(address, "last_ledger_time")


async def update_last_ledger_time(address: str, event_time: int) -> None:
    await _update_event_cursor(address, "last_ledger_time", event_time)


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
        logger.exception("Failed to get setting for %s.", key)
        raise


async def set_setting(key: str, value: str) -> None:
    """Set or update a global bot setting."""
    db = await get_db()
    try:
        async with _db_write_lock:
            await db.execute(
                "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to set setting for %s.", key)
        raise


async def is_event_processed(event_key: str) -> bool:
    """Return whether an event has already been durably handled."""
    db = await get_db()
    async with db.execute(
        "SELECT 1 FROM processed_events WHERE event_key = ?", (event_key,)
    ) as cursor:
        return await cursor.fetchone() is not None


async def get_unprocessed_event_keys(event_keys: list[str]) -> set[str]:
    """Return the subset of keys not present in durable dedup history."""
    if not event_keys:
        return set()
    db = await get_db()
    processed: set[str] = set()
    for start in range(0, len(event_keys), 500):
        chunk = event_keys[start : start + 500]
        placeholders = ",".join("?" for _ in chunk)
        async with db.execute(
            f"SELECT event_key FROM processed_events WHERE event_key IN ({placeholders})",
            chunk,
        ) as cursor:
            processed.update(row[0] for row in await cursor.fetchall())
    return set(event_keys) - processed


async def record_events(
    event_keys: list[tuple[str, int]],
    *,
    notification_key: str | None = None,
    address: str = "",
    notify_type: str = "",
    message: str | None = None,
) -> bool:
    """Atomically mark events processed and optionally enqueue one notification.

    Returns ``True`` when at least one previously unseen event was recorded.
    The unique notification key makes retries and reconnect snapshots idempotent.
    """
    if not event_keys:
        return False
    if message is not None and not notification_key:
        raise ValueError("notification_key is required when message is provided")

    db = await get_db()
    now_ms = int(time.time() * 1000)
    async with _db_write_lock:
        try:
            await db.execute("BEGIN IMMEDIATE")
            inserted = 0
            for event_key, event_time in event_keys:
                cursor = await db.execute(
                    "INSERT OR IGNORE INTO processed_events "
                    "(event_key, event_time, processed_at) VALUES (?, ?, ?)",
                    (event_key, int(event_time or 0), now_ms),
                )
                inserted += max(cursor.rowcount, 0)

            if inserted and message is not None:
                await db.execute(
                    "INSERT OR IGNORE INTO notification_outbox "
                    "(notification_key, address, notify_type, message, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (notification_key, address.lower(), notify_type, message, now_ms),
                )
            await db.commit()
            return inserted > 0
        except Exception:
            await db.rollback()
            logger.exception("Failed to record events/outbox notification.")
            raise


async def get_due_notifications(limit: int = 50) -> list[dict]:
    """Return unsent outbox rows whose retry time has arrived."""
    db = await get_db()
    now_ms = int(time.time() * 1000)
    async with db.execute(
        "SELECT id, notification_key, address, notify_type, message, attempts "
        "FROM notification_outbox "
        "WHERE sent_at IS NULL AND failed_at IS NULL AND next_attempt_at <= ? "
        "ORDER BY id LIMIT ?",
        (now_ms, limit),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def mark_notification_sent(notification_id: int) -> None:
    db = await get_db()
    async with _db_write_lock:
        await db.execute(
            "UPDATE notification_outbox SET sent_at = ?, last_error = NULL WHERE id = ?",
            (int(time.time() * 1000), notification_id),
        )
        await db.commit()


async def reschedule_notification(
    notification_id: int, error: str, delay_seconds: float
) -> None:
    db = await get_db()
    next_attempt_at = int((time.time() + max(delay_seconds, 0)) * 1000)
    async with _db_write_lock:
        await db.execute(
            "UPDATE notification_outbox "
            "SET attempts = attempts + 1, next_attempt_at = ?, last_error = ? "
            "WHERE id = ? AND sent_at IS NULL",
            (next_attempt_at, error[:500], notification_id),
        )
        await db.commit()


async def mark_notification_failed(notification_id: int, error: str) -> None:
    """Archive a permanently undeliverable notification."""
    db = await get_db()
    async with _db_write_lock:
        await db.execute(
            "UPDATE notification_outbox "
            "SET failed_at = ?, last_error = ? "
            "WHERE id = ? AND sent_at IS NULL",
            (int(time.time() * 1000), error[:500], notification_id),
        )
        await db.commit()


async def get_pending_notification_count() -> int:
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM notification_outbox "
        "WHERE sent_at IS NULL AND failed_at IS NULL"
    ) as cursor:
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


async def cleanup_event_history() -> None:
    """Bound durable dedup/outbox history without touching pending messages."""
    db = await get_db()
    now_ms = int(time.time() * 1000)
    processed_cutoff = now_ms - 30 * 24 * 60 * 60 * 1000
    sent_cutoff = now_ms - 7 * 24 * 60 * 60 * 1000
    async with _db_write_lock:
        await db.execute(
            "DELETE FROM processed_events WHERE processed_at < ?", (processed_cutoff,)
        )
        await db.execute(
            "DELETE FROM notification_outbox "
            "WHERE (sent_at IS NOT NULL AND sent_at < ?) "
            "OR (failed_at IS NOT NULL AND failed_at < ?)",
            (sent_cutoff, sent_cutoff),
        )
        await db.commit()

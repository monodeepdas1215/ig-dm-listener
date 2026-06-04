import asyncpg
from datetime import datetime
import json
import logging
from typing import Any, List, Dict

from app.config import settings
from app.schemas.db import LifecycleState

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


# ---------------------------------------------------------------------------
# Pool lifecycle
# ---------------------------------------------------------------------------

async def get_pool() -> asyncpg.Pool:
    """Return the module-level connection pool, creating it if necessary."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
        )
    return _pool


async def close_pool() -> None:
    """Drain and close the connection pool. Called on app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Schema management
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create the pool and ensure the reel_analysis and task_details tables exist.

    When settings.drop_db_on_start is True the tables are dropped first
    (useful for development resets).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if settings.drop_db_on_start:
            await conn.execute("DROP TABLE IF EXISTS reel_analysis")
            await conn.execute("DROP TABLE IF EXISTS task_details")
            logger.info("Dropped existing tables (DROP_DB_ON_START=true).")

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reel_analysis (
                message_id       TEXT PRIMARY KEY,
                thread_id        TEXT,
                timestamp        TEXT,
                video_url        TEXT,
                shortcode        TEXT,
                reel_url         TEXT,
                media_pk         TEXT,
                local_path       TEXT,
                summary_json     TEXT,
                creator_username TEXT,
                lifecycle_state  TEXT NOT NULL DEFAULT 'ONGOING',
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_details (
                task_id          TEXT PRIMARY KEY,
                graph_name       TEXT NOT NULL,
                input_text       TEXT,
                status           TEXT NOT NULL DEFAULT 'PENDING',
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at       TIMESTAMPTZ,
                completed_at     TIMESTAMPTZ,
                error_message    TEXT
            )
            """
        )
    logger.info("Initialized reel_analysis and task_details tables.")


async def ensure_db() -> None:
    """Idempotently ensure the tables exist (does NOT drop them first)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reel_analysis (
                message_id       TEXT PRIMARY KEY,
                thread_id        TEXT,
                timestamp        TEXT,
                video_url        TEXT,
                shortcode        TEXT,
                reel_url         TEXT,
                media_pk         TEXT,
                local_path       TEXT,
                summary_json     TEXT,
                creator_username TEXT,
                lifecycle_state  TEXT NOT NULL DEFAULT 'ONGOING',
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # Attempt to add creator_username column to existing database
        try:
            await conn.execute("ALTER TABLE reel_analysis ADD COLUMN creator_username TEXT")
            logger.info("Added creator_username column to reel_analysis table.")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate_column" in str(e).lower():
                pass
            else:
                logger.warning(f"Failed to check/add creator_username column: {e}")

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_details (
                task_id          TEXT PRIMARY KEY,
                graph_name       TEXT NOT NULL,
                input_text       TEXT,
                status           TEXT NOT NULL DEFAULT 'PENDING',
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at       TIMESTAMPTZ,
                completed_at     TIMESTAMPTZ,
                error_message    TEXT
            )
            """
        )
    logger.info("Ensured reel_analysis and task_details tables exist.")


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

async def insert_reel_ongoing(
    message_id: str,
    thread_id: str,
    timestamp: str,
    video_url: str,
    shortcode: str,
    reel_url: str,
    media_pk: str,
    creator_username: str = "",
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reel_analysis
                (message_id, thread_id, timestamp, video_url, shortcode,
                 reel_url, media_pk, creator_username, lifecycle_state, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            ON CONFLICT (message_id) DO UPDATE
                SET thread_id        = EXCLUDED.thread_id,
                    timestamp        = EXCLUDED.timestamp,
                    video_url        = EXCLUDED.video_url,
                    shortcode        = EXCLUDED.shortcode,
                    reel_url         = EXCLUDED.reel_url,
                    media_pk         = EXCLUDED.media_pk,
                    creator_username = COALESCE(NULLIF(EXCLUDED.creator_username, ''), reel_analysis.creator_username),
                    lifecycle_state  = EXCLUDED.lifecycle_state,
                    updated_at       = NOW()
            """,
            message_id, thread_id, timestamp, video_url, shortcode,
            reel_url, media_pk, creator_username, LifecycleState.ONGOING.value,
        )


async def update_reel_downloaded(
    message_id: str, local_path: str, media_pk: str = "", creator_username: str = ""
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if creator_username:
            if media_pk:
                await conn.execute(
                    """
                    UPDATE reel_analysis
                    SET local_path = $1, media_pk = $2, creator_username = $3,
                        lifecycle_state = $4, updated_at = NOW()
                    WHERE message_id = $5
                    """,
                    local_path, media_pk, creator_username, LifecycleState.DOWNLOADED.value, message_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE reel_analysis
                    SET local_path = $1, creator_username = $2,
                        lifecycle_state = $3, updated_at = NOW()
                    WHERE message_id = $4
                    """,
                    local_path, creator_username, LifecycleState.DOWNLOADED.value, message_id,
                )
        else:
            if media_pk:
                await conn.execute(
                    """
                    UPDATE reel_analysis
                    SET local_path = $1, media_pk = $2,
                        lifecycle_state = $3, updated_at = NOW()
                    WHERE message_id = $4
                    """,
                    local_path, media_pk, LifecycleState.DOWNLOADED.value, message_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE reel_analysis
                    SET local_path = $1, lifecycle_state = $2, updated_at = NOW()
                    WHERE message_id = $3
                    """,
                    local_path, LifecycleState.DOWNLOADED.value, message_id,
                )


async def update_reel_analyzed(
    message_id: str, summary_json: str | dict[str, Any]
) -> None:
    if isinstance(summary_json, dict):
        summary_json = json.dumps(summary_json)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE reel_analysis
            SET summary_json = $1, lifecycle_state = $2, updated_at = NOW()
            WHERE message_id = $3
            """,
            summary_json, LifecycleState.ANALYZED.value, message_id,
        )


async def update_lifecycle_state(
    message_id: str, new_state: LifecycleState
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE reel_analysis
            SET lifecycle_state = $1, updated_at = NOW()
            WHERE message_id = $2
            """,
            new_state.value, message_id,
        )


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

async def get_analyzed_message_ids(limit: int = 100) -> set[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT message_id FROM reel_analysis
            WHERE lifecycle_state IN ($1, $2)
            ORDER BY updated_at DESC
            LIMIT $3
            """,
            LifecycleState.ANALYZED.value, LifecycleState.SYNCED.value, limit,
        )
        return {row["message_id"] for row in rows}


async def update_reel_synced(message_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE reel_analysis
            SET lifecycle_state = $1, updated_at = NOW()
            WHERE message_id = $2
            """,
            LifecycleState.SYNCED.value, message_id,
        )


async def get_reel_by_message_id(message_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM reel_analysis WHERE message_id = $1",
            message_id,
        )
        return dict(row) if row else None


async def get_analyzed_unsynced_records(limit: int = 50) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM reel_analysis
            WHERE lifecycle_state = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            LifecycleState.ANALYZED.value, limit,
        )
        return [dict(row) for row in rows]


async def get_reels_by_lifecycle(state: LifecycleState) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM reel_analysis
            WHERE lifecycle_state = $1
            ORDER BY updated_at DESC
            """,
            state.value,
        )
        return [dict(row) for row in rows]


async def get_stale_or_failed_records(
    threshold_minutes: int, limit: int = 5
) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM reel_analysis
            WHERE lifecycle_state = ANY($1::text[])
              AND updated_at <= NOW() - ($2 * INTERVAL '1 minute')
            ORDER BY created_at ASC
            LIMIT $3
            """,
            [
                LifecycleState.ONGOING.value,
                LifecycleState.DOWNLOADED.value,
                LifecycleState.ANALYZED.value,
                LifecycleState.FAILED.value,
                LifecycleState.RETRYING.value,
            ],
            threshold_minutes,
            limit,
        )
        return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Task operations
# ---------------------------------------------------------------------------

async def create_task_record(task_id: str, graph_name: str, input_text: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO task_details (task_id, graph_name, input_text, status, created_at)
            VALUES ($1, $2, $3, 'PENDING', NOW())
            """,
            task_id, graph_name, input_text
        )


async def update_task_status(
    task_id: str,
    status: str,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    error_message: str | None = None
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if started_at:
            await conn.execute(
                """
                UPDATE task_details
                SET status = $1, started_at = $2
                WHERE task_id = $3
                """,
                status, started_at, task_id
            )
        elif completed_at:
            await conn.execute(
                """
                UPDATE task_details
                SET status = $1, completed_at = $2, error_message = $3
                WHERE task_id = $4
                """,
                status, completed_at, error_message, task_id
            )
        else:
            await conn.execute(
                """
                UPDATE task_details
                SET status = $1
                WHERE task_id = $2
                """,
                status, task_id
            )


async def get_task_status(task_id: str) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM task_details WHERE task_id = $1",
            task_id
        )
        return row["status"] if row else None


async def get_pending_tasks() -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT task_id, graph_name, input_text
            FROM task_details
            WHERE status = 'PENDING'
            ORDER BY created_at ASC
            """
        )
        return [dict(row) for row in rows]


async def fail_interrupted_tasks() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE task_details
            SET status = 'FAILED', completed_at = NOW(),
                error_message = 'Task interrupted by worker shutdown/crash'
            WHERE status = 'RUNNING'
            """
        )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

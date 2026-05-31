import asyncpg
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
    """Create the pool and ensure the reel_analysis table exists.

    When settings.drop_db_on_start is True the table is dropped first
    (useful for development resets).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if settings.drop_db_on_start:
            await conn.execute("DROP TABLE IF EXISTS reel_analysis")
            logger.info("Dropped existing reel_analysis table (DROP_DB_ON_START=true).")

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
                lifecycle_state  TEXT NOT NULL DEFAULT 'ONGOING',
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    logger.info("Initialized reel_analysis table.")


async def ensure_db() -> None:
    """Idempotently ensure the table exists (does NOT drop it first)."""
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
                lifecycle_state  TEXT NOT NULL DEFAULT 'ONGOING',
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    logger.info("Ensured reel_analysis table exists.")


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
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO reel_analysis
                (message_id, thread_id, timestamp, video_url, shortcode,
                 reel_url, media_pk, lifecycle_state, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (message_id) DO UPDATE
                SET thread_id       = EXCLUDED.thread_id,
                    timestamp       = EXCLUDED.timestamp,
                    video_url       = EXCLUDED.video_url,
                    shortcode       = EXCLUDED.shortcode,
                    reel_url        = EXCLUDED.reel_url,
                    media_pk        = EXCLUDED.media_pk,
                    lifecycle_state = EXCLUDED.lifecycle_state,
                    updated_at      = NOW()
            """,
            message_id, thread_id, timestamp, video_url, shortcode,
            reel_url, media_pk, LifecycleState.ONGOING.value,
        )


async def update_reel_downloaded(
    message_id: str, local_path: str, media_pk: str = ""
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
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
            WHERE lifecycle_state = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            LifecycleState.ANALYZED.value, limit,
        )
        return {row["message_id"] for row in rows}


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
              AND created_at <= NOW() - ($2 * INTERVAL '1 minute')
            ORDER BY created_at ASC
            LIMIT $3
            """,
            [LifecycleState.ONGOING.value, LifecycleState.FAILED.value],
            threshold_minutes,
            limit,
        )
        return [dict(row) for row in rows]

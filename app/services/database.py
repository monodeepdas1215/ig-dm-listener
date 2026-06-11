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
                chunk_manifest   TEXT,
                creator_username TEXT,
                lifecycle_state  TEXT NOT NULL DEFAULT 'READ',
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
                chunk_manifest   TEXT,
                creator_username TEXT,
                lifecycle_state  TEXT NOT NULL DEFAULT 'READ',
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # Attempt to add new columns to existing database
        for alter_stmt, log_msg in [
            ("ALTER TABLE reel_analysis ADD COLUMN creator_username TEXT", "creator_username"),
            ("ALTER TABLE reel_analysis ADD COLUMN chunk_manifest TEXT", "chunk_manifest"),
        ]:
            try:
                await conn.execute(alter_stmt)
                logger.info(f"Added {log_msg} column to reel_analysis table.")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate_column" in str(e).lower():
                    pass
                else:
                    logger.warning(f"Failed to check/add {log_msg} column: {e}")

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

async def insert_reel_read(
    message_id: str, thread_id: str, timestamp: str,
    video_url: str, shortcode: str, reel_url: str,
    media_pk: str, creator_username: str = "",
) -> bool:
    """Insert a new reel record with READ state. Returns False if already exists (dedup)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO reel_analysis
                (message_id, thread_id, timestamp, video_url, shortcode,
                 reel_url, media_pk, creator_username, lifecycle_state, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            ON CONFLICT (message_id) DO NOTHING
            """,
            message_id, thread_id, timestamp, video_url, shortcode,
            reel_url, media_pk, creator_username, LifecycleState.READ.value,
        )
        return result == "INSERT 0 1"


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

async def update_reel_chunked(
    message_id: str, chunk_manifest_json: str
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE reel_analysis
            SET chunk_manifest = $1, lifecycle_state = $2, updated_at = NOW()
            WHERE message_id = $3
            """,
            chunk_manifest_json, LifecycleState.CHUNKED.value, message_id,
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

async def update_reel_completed(message_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE reel_analysis
            SET lifecycle_state = $1, updated_at = NOW()
            WHERE message_id = $2
            """,
            LifecycleState.COMPLETED.value, message_id,
        )


from app.schemas.lifecycle_state_machine import LIFECYCLE_STATE_MACHINE

async def update_lifecycle_state(
    message_id: str, new_state: LifecycleState
) -> None:
    """Atomically validate and execute a lifecycle state transition.
    
    Uses an explicit transaction to ensure the SELECT + UPDATE are atomic.
    Prevents race conditions where two concurrent callers read the same
    current state and both attempt to transition.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT lifecycle_state FROM reel_analysis WHERE message_id = $1 FOR UPDATE",
                message_id,
            )
            if not row:
                raise ValueError(f"No record found for message_id={message_id}")
            
            current = LifecycleState(row["lifecycle_state"])
            LIFECYCLE_STATE_MACHINE.transition(current, new_state)  # raises InvalidStateTransition
            
            await conn.execute(
                "UPDATE reel_analysis SET lifecycle_state = $1, updated_at = NOW() WHERE message_id = $2",
                new_state.value, message_id,
            )


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

async def get_reel_by_message_id(message_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM reel_analysis WHERE message_id = $1",
            message_id,
        )
        return dict(row) if row else None


async def get_reels_by_lifecycle_batch(state: LifecycleState, limit: int = 50) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM reel_analysis
            WHERE lifecycle_state = $1
            ORDER BY updated_at ASC
            LIMIT $2
            """,
            state.value, limit
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

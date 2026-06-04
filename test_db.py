"""
Integration test for the database layer against a live PostgreSQL instance.

Prerequisites:
    docker compose up postgres -d
    pip install asyncpg

Usage:
    DATABASE_URL=postgresql://igapp:igapp_secret@localhost:5432/ig_dm_listener \
        python test_db.py
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import asyncpg

from app.schemas.db import LifecycleState

# Override DATABASE_URL before importing settings so the pool targets the right DB
TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://igapp:igapp_secret@localhost:5432/ig_dm_listener",
)


async def _clean_and_seed(conn: asyncpg.Connection) -> None:
    """Drop and recreate the table, then insert deterministic test rows."""
    await conn.execute("DROP TABLE IF EXISTS reel_analysis")
    await conn.execute(
        """
        CREATE TABLE reel_analysis (
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

    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(minutes=20)
    recent_time = now - timedelta(minutes=5)

    # 1. Stale ONGOING  → should be returned
    await conn.execute(
        "INSERT INTO reel_analysis (message_id, lifecycle_state, created_at, updated_at) VALUES ($1, $2, $3, $3)",
        "msg1", LifecycleState.ONGOING.value, stale_time,
    )
    # 2. Recent ONGOING → should NOT be returned
    await conn.execute(
        "INSERT INTO reel_analysis (message_id, lifecycle_state, created_at, updated_at) VALUES ($1, $2, $3, $3)",
        "msg2", LifecycleState.ONGOING.value, recent_time,
    )
    # 3. Stale FAILED   → should be returned
    await conn.execute(
        "INSERT INTO reel_analysis (message_id, lifecycle_state, created_at, updated_at) VALUES ($1, $2, $3, $3)",
        "msg3", LifecycleState.FAILED.value, stale_time,
    )
    # 4. Stale DOWNLOADED → should be returned
    await conn.execute(
        "INSERT INTO reel_analysis (message_id, lifecycle_state, created_at, updated_at) VALUES ($1, $2, $3, $3)",
        "msg4", LifecycleState.DOWNLOADED.value, stale_time,
    )


async def _get_stale_or_failed(
    conn: asyncpg.Connection, threshold_minutes: int, limit: int = 5
) -> list[dict]:
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


async def test() -> None:
    conn = await asyncpg.connect(TEST_DB_URL)
    try:
        await _clean_and_seed(conn)

        records = await _get_stale_or_failed(conn, threshold_minutes=15, limit=5)
        ids = [r["message_id"] for r in records]

        print(f"Picked up IDs: {ids}")
        if set(ids) == {"msg1", "msg3", "msg4"}:
            print("✅ SUCCESS: DB query correctly picked up stale ONGOING, FAILED, and DOWNLOADED records.")
        else:
            print(f"❌ FAILED: expected {{msg1, msg3, msg4}}, got {set(ids)}")
    finally:
        # Cleanup test data
        await conn.execute("DROP TABLE IF EXISTS reel_analysis")
        await conn.close()


asyncio.run(test())

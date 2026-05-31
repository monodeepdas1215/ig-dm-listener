import logging
from typing import Any

from agent_framework.graphs.backfill_reel_info.base_node import BackfillBaseNode
from agent_framework.graphs.backfill_reel_info.state import BackfillReelInfoState
from app.config import settings
from app.schemas.db import LifecycleState
from app.services.database import ensure_db, get_stale_or_failed_records, update_lifecycle_state

logger = logging.getLogger(__name__)

class ReadNRecordsNode(BackfillBaseNode):
    async def run(self, state: BackfillReelInfoState) -> dict[str, Any]:
        logger.info("Ensuring database is initialized...")
        await ensure_db()

        threshold = settings.backfill_stale_threshold_minutes
        limit = settings.backfill_batch_size
        
        logger.info(f"Fetching up to {limit} records stale for {threshold} minutes...")
        records = await get_stale_or_failed_records(threshold, limit)
        
        if not records:
            logger.info("No stale/failed records found.")
            return {"stale_records": [], "record_ids": []}
            
        logger.info(f"Found {len(records)} records. Marking as RETRYING...")
        
        record_ids = []
        for r in records:
            msg_id = r["message_id"]
            await update_lifecycle_state(msg_id, LifecycleState.RETRYING)
            record_ids.append(msg_id)
            
        return {
            "stale_records": records,
            "record_ids": record_ids
        }

import logging
from typing import Any

from agent_framework.graphs.knowledge_base_sync.base_node import KBSyncBaseNode
from agent_framework.graphs.knowledge_base_sync.state import KBSyncState
from app.config import settings
from app.services.database import get_reels_by_lifecycle_batch
from app.schemas.lifecycle_state_machine import LifecycleState

logger = logging.getLogger(__name__)

class FetchAnalyzedRecordsNode(KBSyncBaseNode):
    async def run(self, state: KBSyncState) -> dict[str, Any]:
        logger.info(f"Fetching analyzed records (limit: {settings.kb_sync_batch_size})...")
        
        records = await get_reels_by_lifecycle_batch(
            LifecycleState.ANALYZED, 
            limit=settings.kb_sync_batch_size
        )
        
        if not records:
            logger.info("No records in ANALYZED state found.")
            return {"analyzed_records": []}
            
        logger.info(f"Found {len(records)} analyzed records to sync.")
        return {"analyzed_records": records}

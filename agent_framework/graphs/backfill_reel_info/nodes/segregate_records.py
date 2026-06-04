import logging
import os
from typing import Any

from agent_framework.graphs.backfill_reel_info.base_node import BackfillBaseNode
from agent_framework.graphs.backfill_reel_info.state import BackfillReelInfoState
from app.schemas.db import LifecycleState
from app.services.database import update_lifecycle_state

logger = logging.getLogger(__name__)

class SegregateRecordsNode(BackfillBaseNode):
    async def run(self, state: BackfillReelInfoState) -> dict[str, Any]:
        stale_records = state.get("stale_records", [])
        
        requires_download = []
        requires_summary = []
        
        for record in stale_records:
            msg_id = record["message_id"]
            local_path = record.get("local_path")
            summary_json = record.get("summary_json")
            
            # Check if download is needed (only if we don't already have the summary)
            needs_download = False
            if not summary_json:
                if not local_path or not os.path.exists(local_path):
                    needs_download = True
                
            if needs_download:
                requires_download.append(record)
            elif not summary_json:
                requires_summary.append(record)
            else:
                # Already has summary_json, so it's ready to be synced.
                # Ensure the database lifecycle state is set to ANALYZED.
                logger.info(f"Record {msg_id} already has summary_json. Ensuring state is ANALYZED.")
                await update_lifecycle_state(msg_id, LifecycleState.ANALYZED)
                
        logger.info(f"Segregated {len(stale_records)} records: {len(requires_download)} need download, {len(requires_summary)} need summary only.")
        
        return {
            "requires_download": requires_download,
            "requires_summary": requires_summary
        }

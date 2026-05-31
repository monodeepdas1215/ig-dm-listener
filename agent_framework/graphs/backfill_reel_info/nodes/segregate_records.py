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
            
            # Check if download is needed
            needs_download = False
            if not local_path:
                needs_download = True
            elif not os.path.exists(local_path):
                needs_download = True
                
            if needs_download:
                requires_download.append(record)
            elif not summary_json:
                requires_summary.append(record)
            else:
                # Should not happen for ONGOING/FAILED if the system works correctly, 
                # but handle just in case it's actually complete
                logger.warning(f"Record {msg_id} picked up for backfill but appears complete. Marking ANALYZED.")
                await update_lifecycle_state(msg_id, LifecycleState.ANALYZED)
                
        logger.info(f"Segregated {len(stale_records)} records: {len(requires_download)} need download, {len(requires_summary)} need summary only.")
        
        return {
            "requires_download": requires_download,
            "requires_summary": requires_summary
        }

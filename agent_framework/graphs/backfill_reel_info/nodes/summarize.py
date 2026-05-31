import logging
import os
from typing import Any

from agent_framework.graphs.backfill_reel_info.base_node import BackfillBaseNode
from agent_framework.graphs.backfill_reel_info.state import BackfillReelInfoState
from agent_framework.graphs.insta_dm_automation.nodes.analyze_reels import analyze_video_task
from app.services.database import update_reel_analyzed, update_lifecycle_state
from app.schemas.db import LifecycleState

logger = logging.getLogger(__name__)

class SummarizeNode(BackfillBaseNode):
    async def run(self, state: BackfillReelInfoState) -> dict[str, Any]:
        requires_summary = state.get("requires_summary", [])
        if not requires_summary:
            return {"summary_results": []}

        # Load prompts (reusing the main workflow's prompts)
        base_dir = os.path.dirname(__file__)
        prompts_dir = os.path.join(base_dir, "..", "..", "insta_dm_automation", "prompts")
        
        with open(os.path.join(prompts_dir, "system_prompt.md"), "r") as f:
            system_prompt = f.read()
            
        with open(os.path.join(prompts_dir, "user_prompt.md"), "r") as f:
            user_prompt = f.read()

        llm = self.context.llm
        summary_results = []
        
        # Process sequentially
        for record in requires_summary:
            msg_id = record["message_id"]
            local_path = record["local_path"]
            
            try:
                res = await analyze_video_task(llm, system_prompt, user_prompt, msg_id, local_path)
                
                if res and "summary" in res:
                    # Success
                    await update_reel_analyzed(msg_id, res["summary"])
                    summary_results.append({
                        "message_id": msg_id,
                        "status": "success",
                        "error": None
                    })
                else:
                    raise Exception("analyze_video_task returned None or no summary")
                    
            except Exception as e:
                logger.error(f"Backfill summary failed for msg_id={msg_id}: {e}")
                # Genuine failure -> mark FAILED
                await update_lifecycle_state(msg_id, LifecycleState.FAILED)
                summary_results.append({
                    "message_id": msg_id,
                    "status": "failed",
                    "error": str(e)
                })
                
        return {
            "summary_results": summary_results
        }

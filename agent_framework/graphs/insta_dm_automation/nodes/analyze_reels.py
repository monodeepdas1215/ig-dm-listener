import base64
import json
import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent_framework.graphs.insta_dm_automation.base_node import InstaDMBaseNode
from agent_framework.graphs.insta_dm_automation.state import InstaDMState
from agent_framework.graphs.insta_dm_automation.utils import compute_pipeline_status
from app.services.worker_pool import ThrottledPool, ThrottleConfig
from app.schemas.db import LifecycleState
from app.services.resilient_caller import RetryConfig
from app.services.database import update_reel_analyzed, update_lifecycle_state
from app.config import settings

logger = logging.getLogger(__name__)


async def analyze_video_task(llm: Any, system_prompt: str, user_prompt: str, message_id: str, local_path: str) -> dict[str, Any] | None:
    # Exceptions here will be caught and retried by ResilientCaller (if 429)
    with open(local_path, "rb") as f:
        video_b64 = base64.b64encode(f.read()).decode("utf-8")
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=[
                {"type": "text", "text": user_prompt},
                {
                    "type": "media",
                    "mime_type": "video/mp4",
                    "data": video_b64
                }
            ]
        )
    ]
    
    logger.info(f"Invoking LLM for reel message_id={message_id}")
    response = await llm.ainvoke(messages)
    
    content = response.content
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].strip()
        
    summary_json = json.loads(content)
    return {
        "message_id": message_id,
        "local_path": local_path,
        "summary": summary_json
    }

class AnalyzeReelsNode(InstaDMBaseNode):
    async def run(self, state: InstaDMState) -> dict[str, Any]:
        downloaded_files = state.get("downloaded_files", [])
        if not downloaded_files:
            return {"reel_summaries": []}

        # Load prompts
        base_dir = os.path.dirname(__file__)
        prompts_dir = os.path.join(base_dir, "..", "prompts")
        
        with open(os.path.join(prompts_dir, "system_prompt.md"), "r") as f:
            system_prompt = f.read()
            
        with open(os.path.join(prompts_dir, "user_prompt.md"), "r") as f:
            user_prompt = f.read()

        llm = self.context.llm
        
        pool = ThrottledPool(ThrottleConfig(
            max_concurrent=settings.llm_max_concurrent,
            inter_call_delay_max=settings.llm_inter_call_delay_max,
            retry_config=RetryConfig(
                max_retries=settings.retry_max_retries,
                base_delay=settings.retry_base_delay,
                max_delay=settings.retry_max_delay,
            )
        ))

        task_fns = []
        for item in downloaded_files:
            message_id = item["message_id"]
            local_path = item["local_path"]
            task_fns.append(
                lambda mid=message_id, lp=local_path: analyze_video_task(llm, system_prompt, user_prompt, mid, lp)
            )

        logger.info(f"Starting {len(task_fns)} analysis tasks...")
        results = await pool.run(task_fns)
        
        # Separate successes from failures
        reel_summaries = []
        failed_reels = state.get("failed_reels", [])
        
        for i, res in enumerate(results):
            if isinstance(res, Exception) or res is None:
                msg_id = downloaded_files[i]["message_id"] if i < len(downloaded_files) else f"unknown_task_{i}"
                failed_reels.append({"message_id": msg_id, "error": str(res), "stage": "analyze"})
                await update_lifecycle_state(msg_id, LifecycleState.FAILED)
                logger.error(f"Task for message_id={msg_id} failed: {res}")
            else:
                msg_id = res["message_id"]
                summary = res["summary"]
                reel_summaries.append(res)
                await update_reel_analyzed(msg_id, summary)

        status = compute_pipeline_status(len(task_fns), len(reel_summaries))
        logger.info(f"Successfully analyzed {len(reel_summaries)} reels. Pipeline status: {status.value}")
        
        return {
            "reel_summaries": reel_summaries,
            "pipeline_status": status.value,
            "failed_reels": failed_reels
        }

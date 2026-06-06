import base64
import json
import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent_framework.common.video_message_strategy import get_video_strategy
from agent_framework.graphs.insta_dm_automation.base_node import InstaDMBaseNode
from agent_framework.graphs.insta_dm_automation.state import InstaDMState
from agent_framework.graphs.insta_dm_automation.utils import compute_pipeline_status
from app.services.worker_pool import ThrottledPool, ThrottleConfig
from app.schemas.db import LifecycleState
from app.services.resilient_caller import RetryConfig, RESILIENT_CLASSIFIERS
from app.services.database import update_reel_analyzed, update_lifecycle_state
from app.config import settings
from agent_framework.common.video_message_strategy import GlmMapReduceVideoStrategy

logger = logging.getLogger(__name__)


async def analyze_video_task(
    llm: Any,
    system_prompt: str,
    user_prompt: str,
    message_id: str,
    local_path: str,
    provider: str = "google-genai",
    reduce_system_prompt: str | None = None,
    reduce_user_prompt: str | None = None,
    chunk_size_mb: float = 2.0,
    map_max_concurrent: int = 3,
    vision_model: str | None = None,
) -> dict[str, Any] | None:
    # Exceptions here will be caught and retried by ResilientCaller
    strategy = get_video_strategy(provider)
    
    if isinstance(strategy, GlmMapReduceVideoStrategy):
        logger.info(f"GLM map-reduce path for message_id={message_id}")
        if not reduce_system_prompt or not reduce_user_prompt:
            raise ValueError(
                "reduce_system_prompt and reduce_user_prompt are required "
                "for GLM map-reduce video analysis"
            )
        content = await strategy.analyze(
            caller=llm,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            local_path=local_path,
            reduce_system_prompt=reduce_system_prompt,
            reduce_user_prompt=reduce_user_prompt,
            chunk_size_mb=chunk_size_mb,
            map_max_concurrent=map_max_concurrent,
            vision_model=vision_model,
        )
    else:
        logger.info(f"Invoking LLM for reel message_id={message_id} (provider={provider})")
        messages = strategy.build_messages(system_prompt, user_prompt, local_path)
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

        reduce_system_prompt = None
        reduce_user_prompt = None
        reduce_sys_path = os.path.join(prompts_dir, "reduce_system_prompt.md")
        reduce_usr_path = os.path.join(prompts_dir, "reduce_user_prompt.md")
        if os.path.exists(reduce_sys_path) and os.path.exists(reduce_usr_path):
            with open(reduce_sys_path, "r") as f:
                reduce_system_prompt = f.read()
            with open(reduce_usr_path, "r") as f:
                reduce_user_prompt = f.read()

        llm = self.context.llm
        provider = self.context.llm_provider or "google-genai"
        
        pool = ThrottledPool(ThrottleConfig(
            max_concurrent=settings.llm_max_concurrent,
            inter_call_delay_max=settings.llm_inter_call_delay_max,
            retry_config=RetryConfig(
                max_retries=settings.retry_max_retries,
                base_delay=settings.retry_base_delay,
                max_delay=settings.retry_max_delay,
                retryable_classifiers=RESILIENT_CLASSIFIERS,
            )
        ))

        task_fns = []
        for item in downloaded_files:
            message_id = item["message_id"]
            local_path = item["local_path"]
            task_fns.append(
                lambda mid=message_id, lp=local_path: analyze_video_task(
                    llm, system_prompt, user_prompt, mid, lp, 
                    provider=provider,
                    reduce_system_prompt=reduce_system_prompt,
                    reduce_user_prompt=reduce_user_prompt,
                    chunk_size_mb=settings.zai_video_chunk_size_mb,
                    map_max_concurrent=settings.zai_video_map_max_concurrent,
                    vision_model=settings.zai_vision_model,
                )
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

import json
import logging
from typing import Any

from agent_framework.graphs.reel_analysis.base_node import ReelAnalysisBaseNode
from agent_framework.graphs.reel_analysis.state import ReelAnalysisState
from agent_framework.common.video_message_strategy import get_video_strategy, ChunkManifest
from app.services.database import update_reel_analyzed
from app.schemas.lifecycle_state_machine import LifecycleState
from app.services.worker_pool import ThrottledPool, ThrottleConfig
from app.config import settings

logger = logging.getLogger(__name__)

class AnalyzeReelsNode(ReelAnalysisBaseNode):

    def __init__(self, context):
        super().__init__(context)
        self._pool = ThrottledPool(ThrottleConfig(
            max_concurrent=settings.llm_max_concurrent,
            inter_call_delay_max=settings.llm_inter_call_delay_max,
        ))

    async def run(self, state: ReelAnalysisState) -> dict[str, Any]:
        records = state.get("records_to_analyze", [])
        if not records:
            return {"analysis_results": [], "failed_records": []}

        provider = self.context.llm_provider or "google-genai"
        strategy = get_video_strategy(provider)
        
        analysis_results = []
        failed_records = []

        task_fns = []
        for record in records:
            task_fns.append(
                lambda r=record: self._analyze_single(strategy, r)
            )

        # Run concurrently via bounded ThrottledPool
        results = await self._pool.run(task_fns)

        for record, result in zip(records, results):
            if isinstance(result, Exception):
                logger.error(f"Analysis failed for {record['message_id']}: {result}")
                failed_records.append({"message_id": record["message_id"], "error": str(result)})
            else:
                record["lifecycle_state"] = LifecycleState.ANALYZED.value
                record["summary_json"] = result if isinstance(result, str) else json.dumps(result)
                analysis_results.append({
                    "message_id": record["message_id"],
                    "status": "success",
                    "summary": result
                })

        return {
            "analysis_results": analysis_results,
            "failed_records": failed_records,
        }

    async def _analyze_single(self, strategy, record: dict) -> dict:
        local_path = record["local_path"]
        manifest_json = record.get("chunk_manifest")
        
        manifest = None
        if manifest_json:
            try:
                manifest = ChunkManifest.from_dict(json.loads(manifest_json))
            except Exception as e:
                logger.warning(f"Failed to parse chunk_manifest for {record['message_id']}, proceeding without: {e}")

        # Polymorphic: analyze handles both GLM (map/reduce over manifest) 
        # and LangChain (direct multimodal call ignoring manifest)
        summary = await strategy.analyze(
            local_path=local_path,
            llm=self.llm,
            manifest=manifest
        )

        await update_reel_analyzed(record["message_id"], summary)
        return summary

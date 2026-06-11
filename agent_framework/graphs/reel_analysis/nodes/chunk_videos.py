import json
import logging
from typing import Any

from agent_framework.graphs.reel_analysis.base_node import ReelAnalysisBaseNode
from agent_framework.graphs.reel_analysis.state import ReelAnalysisState
from agent_framework.common.video_message_strategy import get_video_strategy
from app.services.database import update_reel_chunked
from app.schemas.lifecycle_state_machine import LifecycleState
from app.config import settings

logger = logging.getLogger(__name__)

class ChunkVideosNode(ReelAnalysisBaseNode):
    async def run(self, state: ReelAnalysisState) -> dict[str, Any]:
        records = state.get("downloaded_records", [])
        if not records:
            return {"records_to_analyze": []}

        provider = self.context.llm_provider or "google-genai"
        strategy = get_video_strategy(provider)
        records_to_analyze = []

        # Polymorphic: strategy.chunk() returns ChunkManifest or None
        # GLM path: splits video, returns manifest → state moves to CHUNKED
        # LangChain path: returns None → record passes through as-is (still DOWNLOADED)
        for record in records:
            message_id = record["message_id"]
            local_path = record["local_path"]

            if record.get("lifecycle_state") == LifecycleState.CHUNKED.value:
                records_to_analyze.append(record)
                logger.info(f"Skipping chunk for {message_id}: already CHUNKED")
                continue

            try:
                manifest = await strategy.chunk(
                    local_path, chunk_size_mb=settings.zai_video_chunk_size_mb
                )

                if manifest is not None:
                    # Strategy produced chunks → persist manifest to DB iteratively
                    manifest_json = json.dumps(manifest.to_dict())
                    await update_reel_chunked(message_id, manifest_json)
                    # Mutate record in-place — it's a dict from state, won't be read again
                    record["chunk_manifest"] = manifest_json
                    records_to_analyze.append(record)
                    logger.info(f"Chunked {message_id}: {len(manifest.chunks)} chunks")
                else:
                    # Strategy doesn't need chunking (e.g., Gemini/OpenAI)
                    # Record passes through as-is (still DOWNLOADED, chunk_manifest=None)
                    records_to_analyze.append(record)
                    logger.info(f"No chunking needed for {message_id} (provider={provider})")

            except Exception as e:
                logger.error(f"Chunking failed for {message_id}: {e}")
                # Record stays at DOWNLOADED — will be retried on next run
                # ffmpeg stream-copy failure = infrastructure issue, not worth a state transition

        return {"records_to_analyze": records_to_analyze}

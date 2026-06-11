import logging
from typing import Any

from agent_framework.graphs.reel_analysis.base_node import ReelAnalysisBaseNode
from agent_framework.graphs.reel_analysis.state import ReelAnalysisState
from app.config import settings
from app.services.database import get_reels_by_lifecycle_batch
from app.schemas.lifecycle_state_machine import LifecycleState

logger = logging.getLogger(__name__)

# Fetches records in DOWNLOADED or CHUNKED state — both are ready for analysis.
class FetchDownloadedRecordsNode(ReelAnalysisBaseNode):
    async def run(self, state: ReelAnalysisState) -> dict[str, Any]:
        logger.info(f"Fetching processable records (limit: {settings.analysis_batch_size})...")

        downloaded_records = await get_reels_by_lifecycle_batch(
            LifecycleState.DOWNLOADED,
            limit=settings.analysis_batch_size
        )

        chunked_records = await get_reels_by_lifecycle_batch(
            LifecycleState.CHUNKED,
            limit=settings.analysis_batch_size
        )

        records = downloaded_records + chunked_records

        if not records:
            logger.info("No records in DOWNLOADED or CHUNKED state found.")
            return {"downloaded_records": []}

        logger.info(
            f"Found {len(downloaded_records)} DOWNLOADED, "
            f"{len(chunked_records)} CHUNKED records to process."
        )
        return {"downloaded_records": records}

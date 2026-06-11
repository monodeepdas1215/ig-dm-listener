import logging
from typing import Any
from agent_framework.graphs.insta_reel_downloader.base_node import InstaReelDownloaderBaseNode
from agent_framework.graphs.insta_reel_downloader.state import InstaReelDownloaderState

logger = logging.getLogger(__name__)

class ReportNode(InstaReelDownloaderBaseNode):
    async def run(self, state: InstaReelDownloaderState) -> dict[str, Any]:
        new_count = len(state.get("new_reels", []))
        dl_count = len(state.get("downloaded_files", []))
        fail_count = len(state.get("failed_reels", []))
        
        report = (
            f"Insta Reel Downloader completed.\n"
            f"New reels found: {new_count}\n"
            f"Successfully downloaded: {dl_count}\n"
            f"Failed to download: {fail_count}"
        )
        logger.info(report)
        return {"final_report": report}

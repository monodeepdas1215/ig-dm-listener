import logging
import os
from typing import Any

from agent_framework.graphs.insta_reel_downloader.base_node import InstaReelDownloaderBaseNode
from agent_framework.graphs.insta_reel_downloader.state import InstaReelDownloaderState
from app.config import settings
from app.services.database import get_reels_by_lifecycle_batch, update_reel_downloaded
from app.schemas.lifecycle_state_machine import LifecycleState
from app.services.instagram_auth import get_instagrapi_client
from app.services.instagram_dm_reader import download_reel_video
from app.services.worker_pool import ThrottledPool, ThrottleConfig
from app.credentials import load_instagram_credentials

logger = logging.getLogger(__name__)

class DownloadReelsNode(InstaReelDownloaderBaseNode):

    def __init__(self, context):
        super().__init__(context)
        self._pool = ThrottledPool(ThrottleConfig(
            max_concurrent=settings.download_max_concurrent,
            inter_call_delay_max=settings.download_inter_call_delay_max,
        ))

    async def run(self, state: InstaReelDownloaderState) -> dict[str, Any]:
        logger.info("Checking for records in READ state to download...")

        records = await get_reels_by_lifecycle_batch(LifecycleState.READ, limit=settings.dm_fetch_limit * 2)
        if not records:
            logger.info("No records in READ state found.")
            return {"downloaded_files": [], "failed_reels": []}

        logger.info(f"Found {len(records)} records in READ state. Starting download.")

        credentials = load_instagram_credentials()
        client = get_instagrapi_client(credentials)
        os.makedirs(settings.download_dir, exist_ok=True)

        downloaded_files = []
        failed_reels = []

        task_fns = []
        for record in records:
            task_fns.append(
                lambda r=record: self._download_single(client, r)
            )

        results = await self._pool.run(task_fns)

        for record, result in zip(records, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to download reel {record['message_id']}: {result}")
                failed_reels.append({"message_id": record["message_id"], "error": str(result)})
            else:
                downloaded_files.append(result)

        return {
            "downloaded_files": downloaded_files,
            "failed_reels": failed_reels,
        }

    async def _download_single(self, client, record: dict) -> dict:
        message_id = record["message_id"]
        shortcode = record["shortcode"]
        media_pk = record["media_pk"]

        local_path = download_reel_video(
            client=client,
            video_url=record["video_url"],
            shortcode=shortcode,
            media_pk=media_pk,
            message_id=message_id,
            download_dir=settings.download_dir,
        )

        if not local_path:
            raise RuntimeError(f"Download returned empty path for {message_id}")

        await update_reel_downloaded(
            message_id=message_id,
            local_path=local_path,
            media_pk=media_pk,
            creator_username=record.get("creator_username", "")
        )

        return {
            "message_id": message_id,
            "local_path": local_path,
        }

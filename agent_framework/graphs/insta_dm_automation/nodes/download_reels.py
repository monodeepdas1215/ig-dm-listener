import asyncio
import logging
import os
from typing import Any

from agent_framework.graphs.insta_dm_automation.base_node import InstaDMBaseNode
from agent_framework.graphs.insta_dm_automation.state import InstaDMState
from agent_framework.graphs.insta_dm_automation.utils import compute_pipeline_status
from app.schemas.db import LifecycleState
from app.services.worker_pool import ThrottledPool, ThrottleConfig
from app.services.resilient_caller import RetryConfig
from app.credentials import load_instagram_credentials
from app.services.instagram_auth import get_instagrapi_client
from app.services.database import update_reel_downloaded, update_lifecycle_state
from app.config import settings
from app.utils import parser

logger = logging.getLogger(__name__)

def extract_video_url(msg: dict[str, Any]) -> str | None:
    if msg.get("clip") and msg["clip"].get("video_url"):
        return msg["clip"]["video_url"]
    if msg.get("xma_share") and msg["xma_share"].get("video_url"):
        return msg["xma_share"]["video_url"]
    return None


async def download_file_task(client: Any, url: str, message_id: str) -> dict[str, str]:
    shortcode = parser.parse_reel_shortcode(url)
    logger.info(f"Downloading reel for message_id={message_id} from {url} with shortcode {shortcode}")
    # Exceptions here will be caught and retried by ResilientCaller (if 429)
    media_pk = client.media_pk_from_code(shortcode)
    # Bypass instagrapi's public GraphQL API fallback which causes 401s
    media = await asyncio.to_thread(client.media_info_v1, media_pk)
    path = await asyncio.to_thread(
        client.video_download_by_url, 
        media.video_url, 
        str(media_pk), 
        settings.download_dir
    )
    
    new_path = os.path.join(settings.download_dir, f"{message_id}.mp4")
    if os.path.exists(new_path):
        os.remove(new_path)
    os.rename(path, new_path)
    logger.info(f"Downloaded and renamed successfully to {new_path}")
    
    creator_username = ""
    if media.user and hasattr(media.user, "username"):
        creator_username = media.user.username
        
    return {
        "message_id": message_id, 
        "local_path": new_path, 
        "media_pk": str(media_pk),
        "creator_username": creator_username
    }

class DownloadReelsNode(InstaDMBaseNode):
    async def run(self, state: InstaDMState) -> dict[str, Any]:
        unread_reels = state.get("unread_reels", [])
        if not unread_reels:
            return {"downloaded_files": []}

        os.makedirs(settings.download_dir, exist_ok=True)

        credentials = load_instagram_credentials()
        client = get_instagrapi_client(credentials)

        pool = ThrottledPool(ThrottleConfig(
            max_concurrent=settings.download_max_concurrent,
            inter_call_delay_max=settings.download_inter_call_delay_max,
            retry_config=RetryConfig(
                max_retries=settings.retry_max_retries,
                base_delay=settings.retry_base_delay,
                max_delay=settings.retry_max_delay,
            )
        ))

        task_fns = []
        for msg in unread_reels:
            message_id = msg.get("id")
            video_url = extract_video_url(msg)
            if video_url and message_id:
                # Use lambda to create callables for retry
                task_fns.append(lambda mid=message_id, url=video_url: download_file_task(client, url, mid))
            else:
                logger.warning(f"Message {message_id} has no valid video_url.")

        logger.info(f"Starting {len(task_fns)} download tasks...")
        results = await pool.run(task_fns)
        
        # Separate successes from failures
        downloaded_files = []
        failed_reels = state.get("failed_reels", [])
        
        for i, res in enumerate(results):
            if isinstance(res, Exception) or res is None:
                # Re-extract the message id for the failed task if possible
                # Since task_fns index matches results index, we can trace it back (or just use msg loop above if order is guaranteed)
                msg = unread_reels[i] if i < len(unread_reels) else {}
                msg_id = msg.get("id", f"unknown_task_{i}")
                
                failed_reels.append({"message_id": msg_id, "error": str(res), "stage": "download"})
                await update_lifecycle_state(msg_id, LifecycleState.FAILED)
                logger.error(f"Task for message_id={msg_id} failed: {res}")
            else:
                # Successfully downloaded
                msg_id = res["message_id"]
                local_path = res["local_path"]
                media_pk = res.get("media_pk", "")
                creator_username = res.get("creator_username", "")
                
                downloaded_files.append({"message_id": msg_id, "local_path": local_path})
                await update_reel_downloaded(msg_id, local_path, media_pk, creator_username)
                
        status = compute_pipeline_status(len(task_fns), len(downloaded_files))
        logger.info(f"Successfully downloaded {len(downloaded_files)} reels. Pipeline status: {status.value}")
        
        return {
            "downloaded_files": downloaded_files,
            "pipeline_status": status.value,
            "failed_reels": failed_reels
        }

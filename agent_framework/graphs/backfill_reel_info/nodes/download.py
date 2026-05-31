import asyncio
import logging
import os
from typing import Any

from agent_framework.graphs.backfill_reel_info.base_node import BackfillBaseNode
from agent_framework.graphs.backfill_reel_info.state import BackfillReelInfoState
from app.credentials import load_instagram_credentials
from app.services.instagram_auth import get_instagrapi_client
from app.services.database import update_reel_downloaded, update_lifecycle_state
from app.schemas.db import LifecycleState
from app.config import settings

logger = logging.getLogger(__name__)

async def backfill_download_task(client: Any, record: dict[str, Any]) -> str:
    """Returns local_path on success, raises Exception on failure."""
    message_id = record["message_id"]
    shortcode = record["shortcode"]
    media_pk = record.get("media_pk")
    
    logger.info(f"Backfill downloading reel for message_id={message_id} with shortcode {shortcode}")
    
    if not media_pk:
        # Fallback if media_pk is missing
        media_pk = client.media_pk_from_code(shortcode)
        
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
    
    return new_path

class DownloadNode(BackfillBaseNode):
    async def run(self, state: BackfillReelInfoState) -> dict[str, Any]:
        requires_download = state.get("requires_download", [])
        if not requires_download:
            return {"download_results": []}

        os.makedirs(settings.download_dir, exist_ok=True)

        credentials = load_instagram_credentials()
        client = get_instagrapi_client(credentials)
        
        download_results = []
        requires_summary = list(state.get("requires_summary", []))
        
        # We process sequentially to prevent data loss on interruption, per user instruction
        for record in requires_download:
            msg_id = record["message_id"]
            try:
                # We do not use the ThrottledPool here because we are running sequentially
                # and this is a background repair job, but we could add a sleep if needed.
                # If we encounter rate limits, ResilientCaller pattern would be better,
                # but for sequential backfill, basic try/except is okay for now.
                local_path = await backfill_download_task(client, record)
                
                # Success
                media_pk = record.get("media_pk", "")
                await update_reel_downloaded(msg_id, local_path, media_pk)
                
                # Check if it also needs summarization
                if not record.get("summary_json"):
                    # Update the record with the new local_path so summarize node has it
                    record_copy = dict(record)
                    record_copy["local_path"] = local_path
                    requires_summary.append(record_copy)
                    
                download_results.append({
                    "message_id": msg_id,
                    "status": "success",
                    "error": None
                })
                
            except Exception as e:
                logger.error(f"Backfill download failed for msg_id={msg_id}: {e}")
                # Genuine failure -> mark FAILED
                await update_lifecycle_state(msg_id, LifecycleState.FAILED)
                download_results.append({
                    "message_id": msg_id,
                    "status": "failed",
                    "error": str(e)
                })
                
        return {
            "download_results": download_results,
            "requires_summary": requires_summary
        }

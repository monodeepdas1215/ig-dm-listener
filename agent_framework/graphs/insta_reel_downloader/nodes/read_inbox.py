import logging
import re
from typing import Any

from agent_framework.graphs.insta_reel_downloader.base_node import InstaReelDownloaderBaseNode
from agent_framework.graphs.insta_reel_downloader.state import InstaReelDownloaderState
from app.config import settings
from app.services.instagram_auth import get_instagrapi_client
from app.services.instagram_dm_reader import read_dm_metadata_for_sender
from app.services.database import insert_reel_read
from app.credentials import load_instagram_credentials

logger = logging.getLogger(__name__)

class ReadInboxNode(InstaReelDownloaderBaseNode):
    async def run(self, state: InstaReelDownloaderState) -> dict[str, Any]:
        logger.info(f"Reading Instagram DM inbox (limit: {settings.dm_fetch_limit})...")

        credentials = load_instagram_credentials()
        client = get_instagrapi_client(credentials)
        insta_username = settings.ig_username
        sender_username = settings.ig_dm_sender_username

        if not sender_username:
            logger.warning("IG_DM_SENDER_USERNAME is not configured. Stopping inbox read.")
            return {"new_reels": [], "insta_username": insta_username, "sender_username": ""}

        result = read_dm_metadata_for_sender(
            client=client,
            sender_username=sender_username,
            message_limit=settings.dm_fetch_limit,
        )
        messages = result["messages"]
        thread_info = result["thread"]
        logger.info(f"Fetched {len(messages)} matching reel messages from {sender_username}.")

        new_reels = []
        for msg in messages:
            clip = msg.get("clip") or {}
            xma = msg.get("xma_share") or {}
            video_url = clip.get("video_url") or xma.get("video_url") or ""
            shortcode = clip.get("code") or ""
            reel_url = clip.get("reel_url") or ""
            media_pk = clip.get("pk") or ""
            creator_username = clip.get("creator_username") or ""

            # Fallback: extract shortcode from video_url
            if not shortcode and video_url:
                m = re.search(r"/reel/([^/?#]+)", video_url)
                if m:
                    shortcode = m.group(1)

            # Fallback: resolve media_pk from shortcode via API
            if not media_pk and shortcode:
                try:
                    media_pk = str(client.media_pk_from_code(shortcode))
                except Exception as e:
                    logger.warning(f"Could not resolve media_pk for shortcode={shortcode}: {e}")

            if not reel_url and shortcode:
                reel_url = f"https://www.instagram.com/reel/{shortcode}/"

            if not video_url:
                logger.debug(f"Skipping non-reel message: {msg['id']}")
                continue

            inserted = await insert_reel_read(
                message_id=msg["id"],
                thread_id=msg.get("thread_id") or thread_info.get("id", ""),
                timestamp=str(msg.get("timestamp", "")),
                video_url=video_url,
                shortcode=shortcode,
                reel_url=reel_url,
                media_pk=media_pk,
                creator_username=creator_username,
            )

            if inserted:
                new_reels.append({
                    "message_id": msg["id"],
                    "thread_id": msg.get("thread_id") or thread_info.get("id", ""),
                    "timestamp": str(msg.get("timestamp", "")),
                    "video_url": video_url,
                    "shortcode": shortcode,
                    "reel_url": reel_url,
                    "media_pk": media_pk,
                    "creator_username": creator_username,
                })
                logger.info(f"New reel found and state set to READ: {msg['id']} (shortcode: {shortcode})")
            else:
                logger.debug(f"Reel already tracked: {msg['id']}")

        return {
            "new_reels": new_reels,
            "insta_username": insta_username,
            "sender_username": sender_username,
        }

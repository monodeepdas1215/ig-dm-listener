import logging
from typing import Any

from agent_framework.graphs.insta_dm_automation.base_node import InstaDMBaseNode
from agent_framework.graphs.insta_dm_automation.state import InstaDMState
from app.config import settings
from app.credentials import load_instagram_credentials
from app.services.instagram_auth import get_instagrapi_client
from app.services.database import get_analyzed_message_ids, insert_reel_ongoing
from app.services.instagram_dm_reader import read_dm_metadata_for_sender
from app.utils import parser

logger = logging.getLogger(__name__)

class FetchMessagesNode(InstaDMBaseNode):

    async def run(self, state: InstaDMState) -> dict[str, Any]:
        logger.info("Fetching messages from Instagram DM reader...")
        limit = 5 # Can be made configurable
        
        credentials = load_instagram_credentials()
        client = get_instagrapi_client(credentials)
        metadata = read_dm_metadata_for_sender(message_limit=limit, client=client)
        
        sender_username = metadata.get("sender_username", settings.ig_dm_sender_username)
        insta_username = settings.ig_username

        logger.info(f"Fetching analyzed message IDs for sender {sender_username}...")
        analyzed_ids = await get_analyzed_message_ids(limit=100)
        logger.info(f"Fetched analyzed message IDs from sender {sender_username}: {len(analyzed_ids)}")
        logger.debug(f"Analyzed IDs: {analyzed_ids}")

        unread_reels = []
        messages = metadata.get("messages", [])
        
        for msg in messages:
            msg_id = msg.get("id")
            thread_id = msg.get("thread_id", "")
            timestamp = str(msg.get("timestamp", ""))
            xma = msg.get("xma_share") or {}
            is_xma_reel = bool(xma.get("video_url") and "reel" in xma.get("video_url", ""))
            
            has_reel = (
                msg.get("has_reel_share", False) or 
                msg.get("clip") is not None or 
                is_xma_reel
            )
            
            if has_reel and msg_id not in analyzed_ids:
                unread_reels.append(msg)
                
                clip = msg.get("clip") or {}
                video_url = clip.get("video_url") or xma.get("video_url") or ""
                
                shortcode = ""
                reel_url = ""
                media_pk = ""
                
                if video_url:
                    try:
                        shortcode = parser.parse_reel_shortcode(video_url)
                        reel_url = f"https://www.instagram.com/reel/{shortcode}/"
                    except Exception as e:
                        logger.warning(f"Failed to parse shortcode from video_url {video_url}: {e}")
                elif clip.get("code"):
                    shortcode = clip["code"]
                    reel_url = clip.get("reel_url") or f"https://www.instagram.com/reel/{shortcode}/"
                
                if shortcode:
                    media_pk = str(clip.get("pk", ""))
                
                creator_username = clip.get("creator_username") or ""
                
                if msg_id:
                    await insert_reel_ongoing(
                        message_id=msg_id, 
                        thread_id=thread_id, 
                        timestamp=timestamp,
                        video_url=video_url, 
                        shortcode=shortcode, 
                        reel_url=reel_url, 
                        media_pk=media_pk,
                        creator_username=creator_username,
                    )

        logger.info(f"Found {len(unread_reels)} new unread reels out of {len(messages)} fetched messages.")

        return {
            "insta_username": insta_username,
            "sender_username": sender_username,
            "unread_reels": unread_reels
        }

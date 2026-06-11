import json
import logging
import os
from typing import Any

from instagrapi import Client

from app.config import settings, IG_DM_SENDER_USERNAME
from app.credentials import InstagramCredentials, load_instagram_credentials
from app.services.instagram_auth import login_instagrapi
from app.utils.dto_converters import convert_thread_metadata, convert_message_metadata


DEFAULT_THREAD_SCAN_LIMIT = 100
logger = logging.getLogger(__name__)


class DirectThreadLookupError(RuntimeError):
    def __init__(self, sender_username: str, lookup: dict[str, Any]) -> None:
        self.sender_username = sender_username
        self.lookup = lookup

        context_items = [
            item.get("text")
            for item in lookup.get("thread_context_items", [])
            if isinstance(item, dict) and item.get("text")
        ]
        details = {
            "status": lookup.get("status"),
            "is_viewer_unconnected": lookup.get("is_viewer_unconnected"),
            "has_reached_message_request_limit": lookup.get("has_reached_message_request_limit"),
            "thread_context": context_items,
        }
        super().__init__(
            f"No existing Instagram DM thread was found for @{sender_username}. "
            f"Lookup details: {json.dumps(details, default=str)}"
        )


def read_dm_metadata_for_sender(
    *,
    message_limit: int = 20,
    sender_username: str | None = None,
    credentials: InstagramCredentials | None = None,
    client: Client | None = None,
) -> dict[str, Any]:
    sender_username = sender_username or settings.ig_dm_sender_username
    if not sender_username:
        raise ValueError(f"Set {IG_DM_SENDER_USERNAME} before reading Instagram DMs.")

    if client is None:
        credentials = credentials or load_instagram_credentials()
        client = login_instagrapi(credentials)

    logger.info(
        "Reading Instagram DM metadata sender_username=%s limit=%s",
        sender_username,
        message_limit,
    )
    logger.info("Resolving sender Instagram user username=%s", sender_username)
    sender_user_id = client.user_id_from_username(sender_username)
    logger.info("Resolved sender Instagram user username=%s", sender_username)
    logger.debug("Sender Instagram user id=%s", sender_user_id)

    logger.info("Looking up direct thread by participant")
    participant_thread = client.direct_thread_by_participants([sender_user_id])
    logger.info("Participant thread lookup completed")
    thread = _thread_from_participant_lookup(client, participant_thread, message_limit)

    if thread is None:
        logger.info("No thread id returned by participant lookup; scanning inboxes")
        thread = _find_thread_in_inboxes(client, sender_user_id, message_limit)

    if thread is None:
        logger.warning("No existing Instagram DM thread found for sender_username=%s", sender_username)
        raise DirectThreadLookupError(sender_username, participant_thread)

    total_messages = len(thread.messages)
    filtered_messages = [
        message for message in thread.messages if _message_is_from_user(message, sender_user_id)
    ]
    logger.info("Thread fetched with message_count=%s", total_messages)
    logger.info(
        "Sender filter applied sender_username=%s before_count=%s after_count=%s",
        sender_username,
        total_messages,
        len(filtered_messages),
    )

    return {
        "sender_username": sender_username,
        "sender_user_id": str(sender_user_id),
        "thread": convert_thread_metadata(thread),
        "messages": [convert_message_metadata(message) for message in filtered_messages],
    }


def download_reel_video(
    *,
    client: Client,
    video_url: str,
    shortcode: str,
    media_pk: str,
    message_id: str,
    download_dir: str,
) -> str:
    logger.info("Downloading reel shortcode=%s media_pk=%s", shortcode, media_pk)
    os.makedirs(download_dir, exist_ok=True)
    local_path = client.clip_download(int(media_pk), folder=download_dir)
    if not local_path:
        raise RuntimeError(f"clip_download returned empty for media_pk={media_pk}")
    logger.info("Downloaded reel shortcode=%s → %s", shortcode, local_path)
    return str(local_path)


def print_dm_metadata_for_sender(*, message_limit: int = 20) -> None:
    metadata = read_dm_metadata_for_sender(message_limit=message_limit)
    print(json.dumps(metadata, indent=2, default=str))
    logger.info("DM metadata JSON output emitted")


def _thread_from_participant_lookup(
    client: Client,
    participant_thread: Any,
    message_limit: int,
) -> Any | None:
    thread_id = _thread_id_from_participant_lookup(participant_thread)

    if not thread_id:
        logger.info("Participant lookup did not return a thread id")
        return None

    logger.info("Fetching direct thread from participant lookup")
    logger.debug("Direct thread id from participant lookup=%s", thread_id)
    return client.direct_thread(thread_id, amount=message_limit)


def _find_thread_in_inboxes(client: Client, sender_user_id: int, message_limit: int) -> Any | None:
    logger.info("Scanning primary inbox for direct thread")
    primary_threads = client.direct_threads(amount=DEFAULT_THREAD_SCAN_LIMIT)
    logger.info("Primary inbox scan completed thread_count=%s", len(primary_threads))
    for thread in primary_threads:
        if _thread_has_user(thread, sender_user_id):
            logger.info("Direct thread found in primary inbox")
            logger.debug("Primary inbox thread id=%s", thread.id)
            return client.direct_thread(thread.id, amount=message_limit)

    logger.info("Scanning pending inbox for direct thread")
    pending_threads = client.direct_pending_inbox(amount=DEFAULT_THREAD_SCAN_LIMIT)
    logger.info("Pending inbox scan completed thread_count=%s", len(pending_threads))
    for thread in pending_threads:
        if _thread_has_user(thread, sender_user_id):
            logger.info("Direct thread found in pending inbox")
            logger.debug("Pending inbox thread id=%s", thread.id)
            return client.direct_thread(thread.id, amount=message_limit)

    logger.info("Direct thread not found in scanned inboxes")
    return None


def _thread_has_user(thread: Any, sender_user_id: int) -> bool:
    return any(str(getattr(user, "pk", "")) == str(sender_user_id) for user in thread.users)


def _message_is_from_user(message: Any, sender_user_id: int) -> bool:
    return str(getattr(message, "user_id", "") or "") == str(sender_user_id)


def _thread_id_from_participant_lookup(thread_lookup: Any) -> int:
    if not isinstance(thread_lookup, dict):
        return int(getattr(thread_lookup, "id"))

    raw_thread = thread_lookup.get("thread", thread_lookup)
    thread_id = raw_thread.get("thread_id") or raw_thread.get("id")

    if not thread_id:
        return 0

    return int(thread_id)

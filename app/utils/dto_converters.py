from typing import Any


def convert_thread_metadata(thread: Any) -> dict[str, Any]:
    users = []
    for user in getattr(thread, "users", []) or []:
        users.append(
            {
                "pk": str(getattr(user, "pk", "")),
                "username": getattr(user, "username", None),
                "full_name": getattr(user, "full_name", None),
                "is_private": getattr(user, "is_private", None),
                "profile_pic_url": str(getattr(user, "profile_pic_url", "")),
            }
        )

    return {
        "id": str(getattr(thread, "id", "")),
        "pk": str(getattr(thread, "pk", "")),
        "thread_title": getattr(thread, "thread_title", None),
        "thread_type": getattr(thread, "thread_type", None),
        "is_group": getattr(thread, "is_group", None),
        "last_activity_at": getattr(thread, "last_activity_at", None),
        "muted": getattr(thread, "muted", None),
        "users": users,
    }


def convert_message_metadata(message: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(message, "id", "")),
        "thread_id": str(getattr(message, "thread_id", "") or ""),
        "user_id": str(getattr(message, "user_id", "") or ""),
        "timestamp": getattr(message, "timestamp", None),
        "item_type": getattr(message, "item_type", None),
        "text": getattr(message, "text", None),
        "has_media": getattr(message, "media", None) is not None,
        "has_media_share": getattr(message, "media_share", None) is not None,
        "has_reel_share": getattr(message, "reel_share", None) is not None,
        "has_story_share": getattr(message, "story_share", None) is not None,
        "reactions": getattr(message, "reactions", None),
        "xma_share": convert_xma_share_metadata(getattr(message, "xma_share", None)),
        "clip": convert_clip_metadata(getattr(message, "clip", None)),
    }


def convert_xma_share_metadata(xma_share: Any) -> dict[str, Any] | None:
    if xma_share is None:
        return None
    return {
        "title": getattr(xma_share, "title", None),
        "video_url": str(getattr(xma_share, "video_url", "") or ""),
        "preview_url": str(getattr(xma_share, "preview_url", "") or ""),
        "header_title_text": getattr(xma_share, "header_title_text", None),
        "preview_media_fbid": getattr(xma_share, "preview_media_fbid", None),
    }


def convert_clip_metadata(clip: Any) -> dict[str, Any] | None:
    if clip is None:
        return None
    code = getattr(clip, "code", None)
    return {
        "pk": str(getattr(clip, "pk", "") or ""),
        "code": code,
        "reel_url": f"https://www.instagram.com/reel/{code}/" if code else None,
        "video_url": str(getattr(clip, "video_url", "") or ""),
        "thumbnail_url": str(getattr(clip, "thumbnail_url", "") or ""),
        "caption_text": getattr(clip, "caption_text", None),
        "like_count": getattr(clip, "like_count", None),
        "play_count": getattr(clip, "play_count", None),
    }

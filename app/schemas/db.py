from enum import Enum
from pydantic import BaseModel
from typing import Any, Optional


class LifecycleState(str, Enum):
    ONGOING = "ONGOING"
    DOWNLOADED = "DOWNLOADED"
    ANALYZED = "ANALYZED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class ReelMetadata(BaseModel):
    message_id: str
    thread_id: str
    timestamp: str
    video_url: str
    shortcode: str
    reel_url: str
    media_pk: str
    local_path: Optional[str] = None
    summary_json: Optional[str] = None
    lifecycle_state: LifecycleState = LifecycleState.ONGOING

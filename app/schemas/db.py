from pydantic import BaseModel
from typing import Any, Optional
from app.schemas.lifecycle_state_machine import LifecycleState


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
    chunk_manifest: Optional[str] = None
    lifecycle_state: LifecycleState = LifecycleState.READ


from typing import Any

from agent_framework.schemas.state import AgentState


class InstaDMState(AgentState):
    """Custom state extending AgentState for the insta-dm-automation pipeline."""
    insta_username: str = ""
    sender_username: str = ""
    unread_reels: list[dict[str, Any]] = []
    downloaded_files: list[dict[str, Any]] = []  # dict with message_id and local_path
    reel_summaries: list[dict[str, Any]] = []    # list of structured JSON responses
    final_report: str = ""
    kb_sync_count: str = ""
    failed_reels: list[dict[str, Any]] = []

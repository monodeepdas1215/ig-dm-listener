from typing import Any
from agent_framework.schemas.state import AgentState

class InstaReelDownloaderState(AgentState):
    """State for the insta-reel-downloader graph."""
    new_reels: list[dict[str, Any]] = []           # Reels newly found in the inbox and inserted
    downloaded_files: list[dict[str, Any]] = []    # Details of successful downloads
    failed_reels: list[dict[str, Any]] = []        # Details of failed downloads
    insta_username: str = ""
    sender_username: str = ""
    final_report: str = ""

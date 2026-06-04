from typing import Any
from agent_framework.schemas.state import AgentState

class BackfillReelInfoState(AgentState):
    """State for the BackfillReelInfoGraph."""
    stale_records: list[dict[str, Any]] = []
    record_ids: list[str] = []
    requires_download: list[dict[str, Any]] = []
    requires_summary: list[dict[str, Any]] = []
    download_results: list[dict[str, Any]] = []   # {"message_id", "status", "error"}
    summary_results: list[dict[str, Any]] = []    # {"message_id", "status", "error"}
    kb_sync_count: str = ""
    backfill_report_path: str = ""

from typing import Any
from agent_framework.schemas.state import AgentState

class KBSyncState(AgentState):
    """State for the knowledge-base-sync graph."""
    analyzed_records: list[dict[str, Any]] = []     # Records in ANALYZED state
    mcp_available: bool = False                     # Result of MCP availability check
    synced_records: list[dict[str, Any]] = []       # {message_id, vault_path}
    failed_records: list[dict[str, Any]] = []       # {message_id, error}
    final_report: str = ""

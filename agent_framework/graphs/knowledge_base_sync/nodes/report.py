import logging
from typing import Any
from agent_framework.graphs.knowledge_base_sync.base_node import KBSyncBaseNode
from agent_framework.graphs.knowledge_base_sync.state import KBSyncState

logger = logging.getLogger(__name__)

class ReportNode(KBSyncBaseNode):
    async def run(self, state: KBSyncState) -> dict[str, Any]:
        records_count = len(state.get("analyzed_records", []))
        sync_count = len(state.get("synced_records", []))
        fail_count = len(state.get("failed_records", []))
        mcp_available = state.get("mcp_available", False)
        
        if not mcp_available:
            report = f"Knowledge Base Sync aborted: MCP vault_write tool unavailable."
        else:
            report = (
                f"Knowledge Base Sync completed.\n"
                f"Records fetched: {records_count}\n"
                f"Successfully synced: {sync_count}\n"
                f"Failed to sync: {fail_count}"
            )
            
        logger.info(report)
        return {"final_report": report}

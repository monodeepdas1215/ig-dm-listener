import logging
from typing import Any

from agent_framework.graphs.knowledge_base_sync.base_node import KBSyncBaseNode
from agent_framework.graphs.knowledge_base_sync.state import KBSyncState
from agent_framework.tools.mcp_loader import McpToolLoader

logger = logging.getLogger(__name__)

class CheckMCPNode(KBSyncBaseNode):
    async def run(self, state: KBSyncState) -> dict[str, Any]:
        records = state.get("analyzed_records", [])
        if not records:
            return {"mcp_available": False}
            
        mcp_loader = self._find_loader(McpToolLoader)
        if not mcp_loader:
            raise RuntimeError("MCPToolLoader not configured for this graph.")
            
        tools = await mcp_loader.load_tools()
        vault_write_tool = next((t for t in tools if t.name == "vault_write"), None)
        
        if not vault_write_tool:
            raise RuntimeError("MCP vault_write tool is unavailable. Aborting sync.")
            
        logger.info("MCP vault_write tool is available.")
        return {"mcp_available": True}

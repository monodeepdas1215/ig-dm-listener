import logging
from typing import Any

from agent_framework.graphs.knowledge_base_sync.base_node import KBSyncBaseNode
from agent_framework.graphs.knowledge_base_sync.state import KBSyncState
from agent_framework.tools.mcp_loader import McpToolLoader
from app.services.database import update_reel_completed
from app.services.obsidian_service import format_reel_note, build_vault_path

logger = logging.getLogger(__name__)

class SyncObsidianNode(KBSyncBaseNode):
    async def run(self, state: KBSyncState) -> dict[str, Any]:
        records = state.get("analyzed_records", [])
        mcp_available = state.get("mcp_available", False)
        
        if not records or not mcp_available:
            return {"synced_records": [], "failed_records": []}
            
        mcp_loader = self._find_loader(McpToolLoader)
        tools = await mcp_loader.load_tools()
        vault_write_tool = next(t for t in tools if t.name == "vault_write")
        
        synced_records = []
        failed_records = []
        
        for record in records:
            message_id = record["message_id"]
            shortcode = record["shortcode"]
            summary_json = record.get("summary_json")
            
            if not summary_json:
                logger.warning(f"No summary found for {message_id}, skipping sync.")
                failed_records.append({"message_id": message_id, "error": "No summary JSON"})
                continue
                
            try:
                summary_data = {}
                if isinstance(summary_json, dict):
                    summary_data = summary_json
                elif isinstance(summary_json, str) and summary_json.strip():
                    text = summary_json.strip()
                    import re
                    import json
                    match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
                    if match:
                        text = match.group(1)
                    try:
                        summary_data = json.loads(text)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse summary_json for {message_id}: {e}")
                
                markdown_content = format_reel_note(record, summary_data, record.get("creator_username", ""))
                
                vault_path = build_vault_path(shortcode, message_id)
                
                await vault_write_tool.ainvoke({
                    "path": vault_path,
                    "content": markdown_content,
                    "mode": "append"
                })
                
                await update_reel_completed(message_id)
                
                synced_records.append({
                    "message_id": message_id,
                    "vault_path": vault_path
                })
                logger.info(f"Successfully synced {message_id} to {vault_path}")
                
            except Exception as e:
                logger.error(f"Failed to sync {message_id} to Obsidian: {e}")
                failed_records.append({"message_id": message_id, "error": str(e)})
                
        return {
            "synced_records": synced_records,
            "failed_records": failed_records
        }

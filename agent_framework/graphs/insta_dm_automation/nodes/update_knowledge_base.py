import logging
from agent_framework.graphs.insta_dm_automation.base_node import InstaDMBaseNode
from agent_framework.graphs.insta_dm_automation.state import InstaDMState
from agent_framework.tools.mcp_loader import McpToolLoader
from app.services.database import get_reel_by_message_id, update_reel_synced, LifecycleState
from app.services.obsidian_service import build_vault_path, format_reel_note, sync_reel_to_obsidian, generate_highlight

logger = logging.getLogger(__name__)


class UpdateKnowledgeBaseNode(InstaDMBaseNode):
    async def run(self, state: InstaDMState) -> dict:
        logger.info("Running UpdateKnowledgeBaseNode for Instagram DM automation...")
        reel_summaries = state.get("reel_summaries", [])
        if not reel_summaries:
            logger.info("No reel summaries found in state to sync to Obsidian.")
            return {"kb_sync_count": "0/0"}

        sender_username = state.get("sender_username", "Unknown")
        synced = 0
        total = len(reel_summaries)

        # 1. Find the McpToolLoader and load Obsidian MCP tools
        mcp_loader = self._find_loader(McpToolLoader)
        if not mcp_loader:
            logger.error("McpToolLoader not found in context tool_loaders.")
            return {"kb_sync_count": f"0/{total}"}

        obsidian_tools = await mcp_loader.load_tools()

        for item in reel_summaries:
            message_id = item["message_id"]
            summary = item["summary"]

            # 2. Fetch full DB record for shortcode, reel_url, location, etc.
            record = await get_reel_by_message_id(message_id)
            if not record:
                logger.warning(f"Reel DB record not found for message_id {message_id}")
                continue

            if record.get("lifecycle_state") == LifecycleState.SYNCED.value:
                logger.info(f"Reel {message_id} is already SYNCED in the database. Skipping Obsidian sync.")
                synced += 1
                continue

            # Prioritize creator_username from DB, fallback to sender_username
            creator_username = record.get("creator_username") or sender_username

            # 3. Generate highlight one-liner via LLM
            highlight = await generate_highlight(self.context.llm, summary)

            # 4. Format note content with highlight
            vault_path = build_vault_path(record.get("shortcode"), message_id)
            content = format_reel_note(record, summary, creator_username, highlight=highlight)

            # 5. Push to Obsidian via MCP tool
            success = await sync_reel_to_obsidian(obsidian_tools, vault_path, content)

            # 5. Update lifecycle state to SYNCED
            if success:
                await update_reel_synced(message_id)
                synced += 1
            else:
                logger.error(f"Failed to sync reel {message_id} to Obsidian")

        logger.info(f"Knowledge Base sync completed. Synced {synced}/{total} reels.")
        return {"kb_sync_count": f"{synced}/{total}"}

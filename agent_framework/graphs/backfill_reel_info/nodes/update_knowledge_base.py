import json
import logging
from agent_framework.graphs.backfill_reel_info.base_node import BackfillBaseNode
from agent_framework.graphs.backfill_reel_info.state import BackfillReelInfoState
from agent_framework.tools.mcp_loader import McpToolLoader
from app.services.database import get_reel_by_message_id, update_reel_synced, LifecycleState
from app.services.obsidian_service import build_vault_path, format_reel_note, sync_reel_to_obsidian, generate_highlight
from app.config import settings

logger = logging.getLogger(__name__)


class BackfillUpdateKnowledgeBaseNode(BackfillBaseNode):
    async def run(self, state: BackfillReelInfoState) -> dict:
        logger.info("Running BackfillUpdateKnowledgeBaseNode...")
        summary_results = state.get("summary_results", [])
        message_ids = [r["message_id"] for r in summary_results if r["status"] == "success"]

        if not message_ids:
            logger.info("No successfully summarized records found to sync to knowledge base.")
            return {"kb_sync_count": "0/0"}

        # 1. Find the McpToolLoader and load Obsidian MCP tools
        mcp_loader = self._find_loader(McpToolLoader)
        if not mcp_loader:
            logger.error("McpToolLoader not found in context tool_loaders.")
            return {"kb_sync_count": f"0/{len(message_ids)}"}

        obsidian_tools = await mcp_loader.load_tools()

        synced = 0
        total = 0

        # We fall back to the config-configured sender_username for backfill
        sender_username = settings.ig_dm_sender_username or "Unknown"

        for message_id in message_ids:
            # 2. Fetch full record from DB
            record = await get_reel_by_message_id(message_id)
            if not record:
                continue

            # We only sync if state is ANALYZED (not SYNCED, not ONGOING, etc.)
            if record.get("lifecycle_state") != LifecycleState.ANALYZED.value:
                continue

            total += 1
            summary_json = record.get("summary_json")
            if not summary_json:
                logger.warning(f"Reel {message_id} is ANALYZED but has no summary_json. Skipping sync.")
                continue

            try:
                summary = json.loads(summary_json)
            except Exception as e:
                logger.error(f"Failed to parse summary_json for reel {message_id}: {e}")
                continue

            # Prioritize creator_username from DB, fallback to sender_username
            creator_username = record.get("creator_username") or sender_username

            # 3. Generate highlight one-liner via LLM
            highlight = await generate_highlight(self.context.llm, summary)

            # 4. Format note, build path, and push to Obsidian
            vault_path = build_vault_path(record.get("shortcode"), message_id)
            content = format_reel_note(record, summary, creator_username, highlight=highlight)

            success = await sync_reel_to_obsidian(obsidian_tools, vault_path, content)
            if success:
                await update_reel_synced(message_id)
                synced += 1

        logger.info(f"Backfill Knowledge Base sync completed. Synced {synced}/{total} reels from this batch.")
        return {"kb_sync_count": f"{synced}/{total}"}

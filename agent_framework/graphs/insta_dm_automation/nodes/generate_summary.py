import json
import logging
from typing import Any

from agent_framework.graphs.insta_dm_automation.base_node import InstaDMBaseNode
from agent_framework.graphs.insta_dm_automation.state import InstaDMState
from agent_framework.schemas.state import PipelineStatus

logger = logging.getLogger(__name__)

class GenerateSummaryNode(InstaDMBaseNode):
    async def run(self, state: InstaDMState) -> dict[str, Any]:
        reel_summaries = state.get("reel_summaries", [])
        pipeline_status = state.get("pipeline_status", PipelineStatus.SUCCESS.value)
        failed_reels = state.get("failed_reels", [])

        insta_username = state.get("insta_username", "Unknown")
        sender_username = state.get("sender_username", "Unknown")
        
        final_report_lines = [
            f"Analysis Report for {insta_username} (Sender: {sender_username})",
            "=" * 50
        ]

        if pipeline_status == PipelineStatus.FAILURE.value:
            final_report_lines.append("⚠️  PIPELINE FAILURE: No reels were successfully processed.")
        elif pipeline_status == PipelineStatus.PARTIAL_SUCCESS.value:
            final_report_lines.append(f"⚠️  PARTIAL SUCCESS: {len(failed_reels)} reel(s) failed.")
            for f in failed_reels:
                final_report_lines.append(f"  - Message ID: {f.get('message_id')} failed at {f.get('stage')}: {f.get('error')}")
                
        if reel_summaries:
            final_report_lines.append("\nSuccessful Analyses:")
            final_report_lines.append("-" * 50)
            
            for item in reel_summaries:
                message_id = item["message_id"]
                summary = item["summary"]
                
                final_report_lines.append(f"\n--- Message ID: {message_id} ---")
                final_report_lines.append(json.dumps(summary, indent=2))
        elif pipeline_status != PipelineStatus.FAILURE.value:
            final_report_lines.append("No reel summaries to report.")

        final_report = "\n".join(final_report_lines)
        logger.info("Generated final summary report.")
        
        return {"final_report": final_report}

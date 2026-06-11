import logging
from typing import Any
from agent_framework.graphs.reel_analysis.base_node import ReelAnalysisBaseNode
from agent_framework.graphs.reel_analysis.state import ReelAnalysisState

logger = logging.getLogger(__name__)

class ReportNode(ReelAnalysisBaseNode):
    async def run(self, state: ReelAnalysisState) -> dict[str, Any]:
        dl_count = len(state.get("downloaded_records", []))
        analyze_count = len(state.get("analysis_results", []))
        fail_count = len(state.get("failed_records", []))
        
        report = (
            f"Reel Analysis completed.\n"
            f"Records fetched: {dl_count}\n"
            f"Successfully analyzed: {analyze_count}\n"
            f"Failed to analyze: {fail_count}"
        )
        logger.info(report)

        for r in state.get("analysis_results", []):
            summary_text = str(r.get("summary", ""))
            preview = summary_text[:300] + "..." if len(summary_text) > 300 else summary_text
            logger.info(f"  OK {r['message_id']}: {preview}")

        for r in state.get("failed_records", []):
            logger.info(f"  FAIL {r['message_id']}: {r.get('error', 'unknown')}")

        return {"final_report": report}

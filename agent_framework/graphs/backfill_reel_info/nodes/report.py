import logging
import os
from datetime import datetime
from typing import Any

from agent_framework.graphs.backfill_reel_info.base_node import BackfillBaseNode
from agent_framework.graphs.backfill_reel_info.state import BackfillReelInfoState
from app.config import settings

logger = logging.getLogger(__name__)

class ReportNode(BackfillBaseNode):
    async def run(self, state: BackfillReelInfoState) -> dict[str, Any]:
        stale_records = state.get("stale_records", [])
        requires_download = state.get("requires_download", [])
        
        # Determine the initial requires_summary vs what we actually summarized
        # The state currently has the updated requires_summary (which includes newly downloaded)
        # We can deduce the "summary only" by comparing lengths
        
        download_results = state.get("download_results", [])
        summary_results = state.get("summary_results", [])
        
        downloads_succeeded = sum(1 for r in download_results if r["status"] == "success")
        downloads_failed = sum(1 for r in download_results if r["status"] == "failed")
        
        summaries_succeeded = sum(1 for r in summary_results if r["status"] == "success")
        summaries_failed = sum(1 for r in summary_results if r["status"] == "failed")
        
        # A record is fully resolved if it either was just summarized successfully, 
        # or (if it only needed download) was downloaded successfully.
        # But wait, every downloaded record needs a summary. So fully resolved = summary success.
        fully_resolved = summaries_succeeded
        
        # Those marked FAILED in this run
        marked_failed = downloads_failed + summaries_failed
        
        timestamp_str = datetime.now().strftime('%Y%m%d-%H%M%S')
        pretty_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        report_lines = [
            "# Backfill Reel Info — Run Report",
            f"**Timestamp**: {pretty_time}",
            f"**Batch Size**: {settings.backfill_batch_size} | **Stale Threshold**: {settings.backfill_stale_threshold_minutes} min",
            "",
            "## Summary",
            "| Metric | Count |",
            "|---|---|",
            f"| Records Picked Up | {len(stale_records)} |",
            f"| Required Download | {len(requires_download)} |",
            f"| Downloads Succeeded | {downloads_succeeded} |",
            f"| Downloads Failed | {downloads_failed} |",
            f"| Summaries Succeeded | {summaries_succeeded} |",
            f"| Summaries Failed | {summaries_failed} |",
            f"| Fully Resolved (→ ANALYZED) | {fully_resolved} |",
            f"| Marked FAILED | {marked_failed} |",
            f"| Obsidian KB Synced | {state.get('kb_sync_count', '—')} |",
            ""
        ]
        
        if download_results:
            report_lines.append("## Download Details")
            report_lines.append("| Message ID | Status | Error |")
            report_lines.append("|---|---|---|")
            for r in download_results:
                icon = "✅ success" if r["status"] == "success" else "❌ failed"
                err = r["error"] or "—"
                # escape pipes in error message if any
                err = str(err).replace("|", "\\|")
                report_lines.append(f"| {r['message_id']} | {icon} | {err} |")
            report_lines.append("")
            
        if summary_results:
            report_lines.append("## Summary Details")
            report_lines.append("| Message ID | Status | Error |")
            report_lines.append("|---|---|---|")
            for r in summary_results:
                icon = "✅ success" if r["status"] == "success" else "❌ failed"
                err = r["error"] or "—"
                err = str(err).replace("|", "\\|")
                report_lines.append(f"| {r['message_id']} | {icon} | {err} |")
            report_lines.append("")

        report_content = "\n".join(report_lines)
        
        # Write to logs directory
        log_dir = settings.log_dir
        os.makedirs(log_dir, exist_ok=True)
        report_path = os.path.join(log_dir, f"backfill-report-{timestamp_str}.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)
            
        logger.info(f"Generated backfill report at {report_path}")
        
        return {"backfill_report_path": report_path}

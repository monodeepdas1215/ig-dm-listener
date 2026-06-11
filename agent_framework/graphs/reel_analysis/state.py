from typing import Any
from agent_framework.schemas.state import AgentState

class ReelAnalysisState(AgentState):
    """State for the reel-analysis graph."""
    downloaded_records: list[dict[str, Any]] = []     # Records fetched from DB (DOWNLOADED state)
    records_to_analyze: list[dict[str, Any]] = []     # Output of chunk node → input of analyze node.
                                                      # Contains ALL records regardless of provider:
                                                      # - GLM: records with chunk_manifest set (state=CHUNKED)
                                                      # - LangChain: records with chunk_manifest=None (state=DOWNLOADED)
    analysis_results: list[dict[str, Any]] = []       # {message_id, status, summary}
    failed_records: list[dict[str, Any]] = []         # {message_id, error}
    final_report: str = ""

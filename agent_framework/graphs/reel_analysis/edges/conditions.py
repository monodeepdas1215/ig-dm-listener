from agent_framework.graphs.reel_analysis.state import ReelAnalysisState

def has_downloaded_records(state: ReelAnalysisState) -> bool:
    return len(state.get("downloaded_records", [])) > 0

def no_downloaded_records(state: ReelAnalysisState) -> bool:
    return len(state.get("downloaded_records", [])) == 0

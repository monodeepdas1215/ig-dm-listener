from agent_framework.graphs.knowledge_base_sync.state import KBSyncState

def has_analyzed_records(state: KBSyncState) -> bool:
    return len(state.get("analyzed_records", [])) > 0

def no_analyzed_records(state: KBSyncState) -> bool:
    return len(state.get("analyzed_records", [])) == 0

def is_mcp_available(state: KBSyncState) -> bool:
    return state.get("mcp_available", False)

def no_mcp_available(state: KBSyncState) -> bool:
    return not state.get("mcp_available", False)

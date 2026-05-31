def has_stale_records(state) -> bool:
    return len(state.get("stale_records", [])) > 0

def no_stale_records(state) -> bool:
    return len(state.get("stale_records", [])) == 0

def has_downloads_needed(state) -> bool:
    return len(state.get("requires_download", [])) > 0

def no_downloads_needed(state) -> bool:
    return len(state.get("requires_download", [])) == 0

def has_summaries_needed(state) -> bool:
    return len(state.get("requires_summary", [])) > 0

def no_summaries_needed(state) -> bool:
    return len(state.get("requires_summary", [])) == 0

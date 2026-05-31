from agent_framework.graphs.insta_dm_automation.state import InstaDMState

def has_unread_reels(state: InstaDMState) -> bool:
    """Returns True if there are unread reels to process."""
    return len(state.get('unread_reels', [])) > 0

def no_unread_reels(state: InstaDMState) -> bool:
    """Returns True if there are NO unread reels to process."""
    return len(state.get('unread_reels', [])) == 0

def has_downloaded_files(state: InstaDMState) -> bool:
    """Proceed to analyze only if at least one reel was downloaded."""
    return len(state.get('downloaded_files', [])) > 0

def no_downloaded_files(state: InstaDMState) -> bool:
    """Skip analysis if download was a total failure."""
    return len(state.get('downloaded_files', [])) == 0

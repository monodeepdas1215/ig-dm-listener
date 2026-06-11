from agent_framework.graphs.insta_reel_downloader.state import InstaReelDownloaderState

def has_new_reels(state: InstaReelDownloaderState) -> bool:
    return len(state.get("new_reels", [])) > 0

def no_new_reels(state: InstaReelDownloaderState) -> bool:
    return len(state.get("new_reels", [])) == 0

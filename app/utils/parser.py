from typing import Any


def parse_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    object_type = payload.get("object")
    entries = payload.get("entry", [])

    return {
        "object": object_type,
        "entries": [_parse_entry(entry) for entry in entries if isinstance(entry, dict)],
    }


def _parse_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "time": entry.get("time"),
        "messaging": entry.get("messaging", []),
        "changes": entry.get("changes", []),
    }

def parse_reel_shortcode(instagram_reel_url: str) -> str:
    reel_url = instagram_reel_url.strip("").split("?")[0][:-1]
    return reel_url.split("/")[-1]
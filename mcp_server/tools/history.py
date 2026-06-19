"""Listening-history implementation logic (HISTORY_* mixes)."""
from typing import Dict, Any


def get_listening_history(make_tidal_request_func) -> Dict[str, Any]:
    """Implementation logic for getting the user's listening-history mixes.

    Returns the HISTORY_* surfaces (alltime / yearly / monthly) with their tier
    and recency order. Fetch each mix's tracks with get_mix_tracks() to turn this
    into a play-frequency/recency signal.
    """
    result = make_tidal_request_func("/api/history")

    if result["status"] != "success":
        return result

    data = result["data"]
    history_mixes = data.get("history_mixes", [])
    response = {
        "status": "success",
        "history_mixes": history_mixes,
        "history_mix_count": len(history_mixes),
    }
    # History is an optional enrichment; surface any warning rather than failing.
    if data.get("warning"):
        response["warning"] = data["warning"]
    return response

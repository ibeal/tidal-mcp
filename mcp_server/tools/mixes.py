"""TIDAL algorithmic mixes implementation logic."""
from typing import Dict, Any


def get_user_mixes(make_tidal_request_func) -> Dict[str, Any]:
    """Implementation logic for getting the user's TIDAL mixes."""
    result = make_tidal_request_func("/api/mixes")

    if result["status"] != "success":
        return result

    data = result["data"]
    mixes = data.get("mixes", [])
    response = {
        "status": "success",
        "mixes": mixes,
        "mix_count": len(mixes),
    }
    # Mixes are best-effort upstream; surface any warning so the model can explain it.
    if data.get("warning"):
        response["warning"] = data["warning"]
    return response


def get_mix_tracks(
    make_tidal_request_func,
    mix_id: str,
    limit: int = 100
) -> Dict[str, Any]:
    """Implementation logic for getting tracks from a specific TIDAL mix."""
    if not mix_id or not mix_id.strip():
        return {
            "status": "error",
            "message": "A mix ID is required. You can get mix IDs by using the get_user_mixes() function."
        }

    params = {"limit": limit}
    result = make_tidal_request_func(f"/api/mixes/{mix_id}/tracks", params)

    if result["status"] != "success":
        return result

    data = result["data"]
    return {
        "status": "success",
        "tracks": data.get("tracks", []),
        "track_count": data.get("count", 0),
    }

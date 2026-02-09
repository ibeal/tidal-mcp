"""Playlist management implementation logic."""
from typing import Dict, Any, Optional, List


def create_tidal_playlist(
    make_tidal_request_func,
    title: str,
    track_ids: list,
    description: str = ""
) -> Dict[str, Any]:
    """Implementation logic for creating a TIDAL playlist."""
    # Validate inputs
    if not title or not title.strip():
        return {
            "status": "error",
            "message": "Playlist title cannot be empty."
        }

    if not track_ids or not isinstance(track_ids, list) or len(track_ids) == 0:
        return {
            "status": "error",
            "message": "You must provide at least one track ID to add to the playlist."
        }

    # Create the playlist through the Flask API
    payload = {
        "title": title.strip(),
        "description": description,
        "track_ids": track_ids
    }

    result = make_tidal_request_func("/api/playlists", payload, method="POST")

    if result["status"] != "success":
        return result

    # Parse the response
    response_data = result["data"]
    playlist_data = response_data.get("playlist", {})

    # Get the playlist ID and add TIDAL URL
    playlist_id = playlist_data.get("id")
    if playlist_id:
        playlist_data["playlist_url"] = f"https://tidal.com/playlist/{playlist_id}"

    return {
        "status": "success",
        "message": f"Successfully created playlist '{title}' with {len(track_ids)} tracks",
        "playlist": playlist_data
    }


def get_user_playlists(make_tidal_request_func) -> Dict[str, Any]:
    """Implementation logic for getting user playlists."""
    result = make_tidal_request_func("/api/playlists")

    if result["status"] != "success":
        return result

    playlists = result["data"].get("playlists", [])
    return {
        "status": "success",
        "playlists": playlists,
        "playlist_count": len(playlists)
    }


def get_playlist_tracks(
    make_tidal_request_func,
    playlist_id: str,
    limit: int = 100
) -> Dict[str, Any]:
    """Implementation logic for getting playlist tracks."""
    # Validate playlist_id
    if not playlist_id or not playlist_id.strip():
        return {
            "status": "error",
            "message": "A playlist ID is required. You can get playlist IDs by using the get_user_playlists() function."
        }

    params = {"limit": limit}
    result = make_tidal_request_func(f"/api/playlists/{playlist_id}/tracks", params)

    if result["status"] != "success":
        return result

    data = result["data"]
    return {
        "status": "success",
        "tracks": data.get("tracks", []),
        "track_count": data.get("total_tracks", 0)
    }


def delete_tidal_playlist(
    make_tidal_request_func,
    playlist_id: str
) -> Dict[str, Any]:
    """Implementation logic for deleting a TIDAL playlist."""
    # Validate playlist_id
    if not playlist_id or not playlist_id.strip():
        return {
            "status": "error",
            "message": "A playlist ID is required. You can get playlist IDs by using the get_user_playlists() function."
        }

    result = make_tidal_request_func(f"/api/playlists/{playlist_id}", method="DELETE")

    if result["status"] == "success":
        return result["data"]
    else:
        return result


def add_tracks_to_playlist(
    make_tidal_request_func,
    playlist_id: str,
    track_ids: list
) -> Dict[str, Any]:
    """Implementation logic for adding tracks to a playlist."""
    # Validate inputs
    if not playlist_id:
        return {
            "status": "error",
            "message": "A playlist ID is required. You can get playlist IDs using get_user_playlists()."
        }

    if not track_ids or not isinstance(track_ids, list):
        return {
            "status": "error",
            "message": "track_ids must be a non-empty list of track IDs."
        }

    result = make_tidal_request_func(
        f"/api/playlists/{playlist_id}/tracks",
        params={"track_ids": track_ids},
        method="POST"
    )

    return result


def remove_tracks_from_playlist(
    make_tidal_request_func,
    playlist_id: str,
    track_ids: Optional[list] = None,
    indices: Optional[list] = None
) -> Dict[str, Any]:
    """Implementation logic for removing tracks from a playlist."""
    # Validate inputs
    if not playlist_id:
        return {
            "status": "error",
            "message": "A playlist ID is required. You can get playlist IDs using get_user_playlists()."
        }

    if not track_ids and not indices:
        return {
            "status": "error",
            "message": "Must provide either track_ids or indices to remove tracks."
        }

    if track_ids and indices:
        return {
            "status": "error",
            "message": "Provide either track_ids OR indices, not both."
        }

    params = {}
    if track_ids:
        params["track_ids"] = track_ids
    if indices:
        params["indices"] = indices

    result = make_tidal_request_func(
        f"/api/playlists/{playlist_id}/tracks",
        params=params,
        method="DELETE"
    )

    return result


def update_playlist_metadata(
    make_tidal_request_func,
    playlist_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Implementation logic for updating playlist metadata."""
    # Validate inputs
    if not playlist_id:
        return {
            "status": "error",
            "message": "A playlist ID is required. You can get playlist IDs using get_user_playlists()."
        }

    if not title and not description:
        return {
            "status": "error",
            "message": "Must provide at least a new title or description."
        }

    params = {}
    if title:
        params["title"] = title
    if description:
        params["description"] = description

    result = make_tidal_request_func(
        f"/api/playlists/{playlist_id}",
        params=params,
        method="PATCH"
    )

    return result


def reorder_playlist_tracks(
    make_tidal_request_func,
    playlist_id: str,
    from_index: int,
    to_index: int
) -> Dict[str, Any]:
    """Implementation logic for reordering playlist tracks."""
    # Validate inputs
    if not playlist_id:
        return {
            "status": "error",
            "message": "A playlist ID is required. You can get playlist IDs using get_user_playlists()."
        }

    if from_index is None or to_index is None:
        return {
            "status": "error",
            "message": "Both from_index and to_index are required."
        }

    if from_index < 0 or to_index < 0:
        return {
            "status": "error",
            "message": "Indices must be non-negative (0-based indexing)."
        }

    result = make_tidal_request_func(
        f"/api/playlists/{playlist_id}/tracks/move",
        params={"from_index": from_index, "to_index": to_index},
        method="POST"
    )

    return result

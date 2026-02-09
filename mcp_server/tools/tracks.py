"""Track and recommendation implementation logic."""
import requests
from typing import Dict, Any, Optional, List


def get_favorite_tracks(flask_app_url: str, limit: int = 20) -> Dict[str, Any]:
    """Implementation logic for getting favorite tracks."""
    try:
        # First, check if the user is authenticated
        auth_check = requests.get(f"{flask_app_url}/api/auth/status")
        auth_data = auth_check.json()

        if not auth_data.get("authenticated", False):
            return {
                "status": "error",
                "message": "You need to login to TIDAL first before I can fetch your favorite tracks. Please use the tidal_login() function."
            }

        # Call your Flask endpoint to retrieve tracks with the specified limit
        response = requests.get(f"{flask_app_url}/api/tracks", params={"limit": limit})

        # Check if the request was successful
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            return {
                "status": "error",
                "message": "Not authenticated with TIDAL. Please login first using tidal_login()."
            }
        else:
            error_data = response.json()
            return {
                "status": "error",
                "message": f"Failed to retrieve tracks: {error_data.get('error', 'Unknown error')}"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to connect to TIDAL tracks service: {str(e)}"
        }


def _get_tidal_recommendations(flask_app_url: str, track_ids: list = None, limit_per_track: int = 20, filter_criteria: str = None) -> Dict[str, Any]:
    """
    [INTERNAL USE] Gets raw recommendation data from TIDAL API.
    This is a lower-level function primarily used by higher-level recommendation functions.
    For end-user recommendations, use recommend_tracks instead.
    """
    try:
        # Validate track_ids
        if not track_ids or not isinstance(track_ids, list) or len(track_ids) == 0:
            return {
                "status": "error",
                "message": "No track IDs provided for recommendations."
            }

        # Call the batch recommendations endpoint
        payload = {
            "track_ids": track_ids,
            "limit_per_track": limit_per_track,
            "remove_duplicates": True
        }

        response = requests.post(f"{flask_app_url}/api/recommendations/batch", json=payload)

        if response.status_code != 200:
            error_data = response.json()
            return {
                "status": "error",
                "message": f"Failed to get recommendations: {error_data.get('error', 'Unknown error')}"
            }

        recommendations = response.json().get("recommendations", [])

        # If filter criteria is provided, include it in the response for LLM processing
        result = {
            "recommendations": recommendations,
            "total_count": len(recommendations)
        }

        if filter_criteria:
            result["filter_criteria"] = filter_criteria

        return result

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to get recommendations: {str(e)}"
        }


def recommend_tracks(flask_app_url: str, get_favorite_tracks_func, track_ids: Optional[List[str]] = None, filter_criteria: Optional[str] = None, limit_per_track: int = 20, limit_from_favorite: int = 20) -> Dict[str, Any]:
    """Implementation logic for track recommendations."""
    # First, check if the user is authenticated
    auth_check = requests.get(f"{flask_app_url}/api/auth/status")
    auth_data = auth_check.json()

    if not auth_data.get("authenticated", False):
        return {
            "status": "error",
            "message": "You need to login to TIDAL first before I can recommend music. Please use the tidal_login() function."
        }

    # Initialize variables to store our seed tracks and their info
    seed_track_ids = []
    seed_tracks_info = []

    # If track_ids are provided, use them directly
    if track_ids and isinstance(track_ids, list) and len(track_ids) > 0:
        seed_track_ids = track_ids
        # Note: We don't have detailed info about these tracks, just IDs
        # This is fine as the recommendation API only needs IDs
    else:
        # If no track_ids provided, get the user's favorite tracks
        tracks_response = get_favorite_tracks_func(limit=limit_from_favorite)

        # Check if we successfully retrieved tracks
        if "status" in tracks_response and tracks_response["status"] == "error":
            return {
                "status": "error",
                "message": f"Unable to get favorite tracks for recommendations: {tracks_response['message']}"
            }

        # Extract the track data
        favorite_tracks = tracks_response.get("tracks", [])

        if not favorite_tracks:
            return {
                "status": "error",
                "message": "I couldn't find any favorite tracks in your TIDAL account to use as seeds for recommendations."
            }

        # Use these as our seed tracks
        seed_track_ids = [track["id"] for track in favorite_tracks]
        seed_tracks_info = favorite_tracks

    # Get recommendations based on the seed tracks
    recommendations_response = _get_tidal_recommendations(
        flask_app_url=flask_app_url,
        track_ids=seed_track_ids,
        limit_per_track=limit_per_track,
        filter_criteria=filter_criteria
    )

    # Check if we successfully retrieved recommendations
    if "status" in recommendations_response and recommendations_response["status"] == "error":
        return {
            "status": "error",
            "message": f"Unable to get recommendations: {recommendations_response['message']}"
        }

    # Get the recommendations
    recommendations = recommendations_response.get("recommendations", [])

    if not recommendations:
        return {
            "status": "error",
            "message": "I couldn't find any recommendations based on the provided tracks. Please try again with different tracks or adjust your filtering criteria."
        }

    # Return the structured data to process
    return {
        "status": "success",
        "seed_tracks": seed_tracks_info,  # This might be empty if direct track_ids were provided
        "seed_track_ids": seed_track_ids,
        "recommendations": recommendations,
        "filter_criteria": filter_criteria,
        "seed_count": len(seed_track_ids),
    }

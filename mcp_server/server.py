from mcp.server.fastmcp import FastMCP
import requests
import atexit
import functools
from typing import Optional, List, Dict, Any, Union

from mcp_server.utils import start_flask_app, shutdown_flask_app, FLASK_APP_URL, FLASK_PORT

# Print the port being used for debugging
print(f"TIDAL MCP starting on port {FLASK_PORT}")

# Create an MCP server
mcp = FastMCP("TIDAL MCP")

# Start the Flask app when this script is loaded
print("MCP server module is being loaded. Starting Flask app...")
start_flask_app()

# Register the shutdown function to be called when the MCP server exits
atexit.register(shutdown_flask_app)

# Constants
VALID_SEARCH_TYPES = ["all", "tracks", "albums", "artists", "playlists"]
AUTH_ERROR_MESSAGE = "You need to login to TIDAL first before using this feature. Please use the tidal_login() function."
EMPTY_QUERY_ERROR = "Search query cannot be empty. Please provide a search term."

# Type aliases for better code clarity
TidalResponse = Dict[str, Any]
SearchResults = Dict[str, Union[str, int, List[Dict[str, Any]]]]

def requires_tidal_auth(func):
    """Decorator to check TIDAL authentication before executing a function."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            auth_check = requests.get(f"{FLASK_APP_URL}/api/auth/status", timeout=5)
            auth_data = auth_check.json()

            if not auth_data.get("authenticated", False):
                return {
                    "status": "error",
                    "message": AUTH_ERROR_MESSAGE
                }

            return func(*args, **kwargs)
        except requests.RequestException as e:
            return {
                "status": "error",
                "message": f"Failed to verify authentication: {str(e)}"
            }
    return wrapper

def validate_search_query(query: str) -> Optional[TidalResponse]:
    """Validate search query input. Returns error dict if invalid, None if valid."""
    if not query or not query.strip():
        return {
            "status": "error",
            "message": EMPTY_QUERY_ERROR
        }
    return None

def make_tidal_request(endpoint: str, params: Optional[Dict[str, Any]] = None, method: str = "GET") -> TidalResponse:
    """Make a request to the TIDAL API with standardized error handling."""
    try:
        url = f"{FLASK_APP_URL}{endpoint}"

        if method.upper() == "GET":
            response = requests.get(url, params=params, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(url, json=params, timeout=10)
        elif method.upper() == "DELETE":
            response = requests.delete(url, timeout=10)
        else:
            return {"status": "error", "message": f"Unsupported HTTP method: {method}"}

        if response.status_code == 200:
            return {"status": "success", "data": response.json()}
        elif response.status_code == 401:
            return {"status": "error", "message": "Authentication expired. Please login again using tidal_login()."}
        elif response.status_code == 404:
            return {"status": "error", "message": "Resource not found."}
        else:
            error_data = response.json() if response.content else {}
            return {
                "status": "error",
                "message": error_data.get('error', f"Request failed with status {response.status_code}")
            }

    except requests.Timeout:
        return {"status": "error", "message": "Request timed out. Please try again."}
    except requests.RequestException as e:
        return {"status": "error", "message": f"Network error: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}

def format_search_results(query: str, result_type: str, data: TidalResponse, extract_key: str) -> SearchResults:
    """Format search results consistently."""
    if data["status"] != "success":
        return data

    response_data = data["data"]
    items = response_data.get("results", {}).get(extract_key, {}).get("items", [])

    return {
        "status": "success",
        "query": query,
        result_type: items,
        f"{result_type.rstrip('s')}_count": len(items)
    }

@mcp.tool()
def tidal_login() -> dict:
    """
    Authenticate with TIDAL through browser login flow.
    This will open a browser window for the user to log in to their TIDAL account.

    Returns:
        A dictionary containing authentication status and user information if successful
    """
    try:
        # Call your Flask endpoint for TIDAL authentication
        response = requests.get(f"{FLASK_APP_URL}/api/auth/login")

        # Check if the request was successful
        if response.status_code == 200:
            return response.json()
        else:
            error_data = response.json()
            return {
                "status": "error",
                "message": f"Authentication failed: {error_data.get('message', 'Unknown error')}"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to connect to TIDAL authentication service: {str(e)}"
        }

@mcp.tool()
def get_favorite_tracks(limit: int = 20) -> dict:
    """
    Retrieves tracks from the user's TIDAL account favorites.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "What are my favorite tracks?"
    - "Show me my TIDAL favorites"
    - "What music do I have saved?"
    - "Get my favorite songs"
    - Any request to view their saved/favorite tracks

    This function retrieves the user's favorite tracks from TIDAL.

    Args:
        limit: Maximum number of tracks to retrieve (default: 20, note it should be large enough by default unless specified otherwise).

    Returns:
        A dictionary containing track information including track ID, title, artist, album, and duration.
        Returns an error message if not authenticated or if retrieval fails.
    """
    try:
        # First, check if the user is authenticated
        auth_check = requests.get(f"{FLASK_APP_URL}/api/auth/status")
        auth_data = auth_check.json()

        if not auth_data.get("authenticated", False):
            return {
                "status": "error",
                "message": "You need to login to TIDAL first before I can fetch your favorite tracks. Please use the tidal_login() function."
            }

        # Call your Flask endpoint to retrieve tracks with the specified limit
        response = requests.get(f"{FLASK_APP_URL}/api/tracks", params={"limit": limit})

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

def _get_tidal_recommendations(track_ids: list = None, limit_per_track: int = 20, filter_criteria: str = None) -> dict:
    """
    [INTERNAL USE] Gets raw recommendation data from TIDAL API.
    This is a lower-level function primarily used by higher-level recommendation functions.
    For end-user recommendations, use recommend_tracks instead.

    Args:
        track_ids: List of TIDAL track IDs to use as seeds for recommendations.
        limit_per_track: Maximum number of recommendations to get per track (default: 20)
        filter_criteria: Optional string describing criteria to filter recommendations
                         (e.g., "relaxing", "new releases", "upbeat")

    Returns:
        A dictionary containing recommended tracks based on seed tracks and filtering criteria.
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

        response = requests.post(f"{FLASK_APP_URL}/api/recommendations/batch", json=payload)

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

@mcp.tool()
def recommend_tracks(track_ids: Optional[List[str]] = None, filter_criteria: Optional[str] = None, limit_per_track: int = 20, limit_from_favorite: int = 20) -> dict:
    """
    Recommends music tracks based on specified track IDs or can use the user's TIDAL favorites if no IDs are provided.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - Music recommendations
    - Track suggestions
    - Music similar to their TIDAL favorites or specific tracks
    - "What should I listen to?"
    - Any request to recommend songs/tracks/music based on their TIDAL history or specific tracks

    This function gets recommendations based on provided track IDs or retrieves the user's
    favorite tracks as seeds if no IDs are specified.

    When processing the results of this tool:
    1. Analyze the seed tracks to understand the music taste or direction
    2. Review the recommended tracks from TIDAL
    3. IMPORTANT: Do NOT include any tracks from the seed tracks in your recommendations
    4. Ensure there are NO DUPLICATES in your recommended tracks list
    5. Select and rank the most appropriate tracks based on the seed tracks and filter criteria
    6. Group recommendations by similar styles, artists, or moods with descriptive headings
    7. For each recommended track, provide:
       - The track name, artist, album
       - Always include the track's URL to make it easy for users to listen to the track
       - A brief explanation of why this track might appeal to the user based on the seed tracks
       - If applicable, how this track matches their specific filter criteria
    8. Format your response as a nicely presented list of recommendations with helpful context (remember to include the track's URL!)
    9. Begin with a brief introduction explaining your selection strategy
    10. Lastly, unless specified otherwise, you should recommend MINIMUM 20 tracks (or more if possible) to give the user a good variety to choose from.

    [IMPORTANT NOTE] If you're not familiar with any artists or tracks mentioned, you should use internet search capabilities if available to provide more accurate information.

    Args:
        track_ids: Optional list of TIDAL track IDs to use as seeds for recommendations.
                  If not provided, will use the user's favorite tracks.
        filter_criteria: Specific preferences for filtering recommendations (e.g., "relaxing music,"
                         "recent releases," "upbeat," "jazz influences")
        limit_per_track: Maximum number of recommendations to get per track (NOTE: default: 20, unless specified otherwise, we'd like to keep the default large enough to have enough candidates to work with)
        limit_from_favorite: Maximum number of favorite tracks to use as seeds (NOTE: default: 20, unless specified otherwise, we'd like to keep the default large enough to have enough candidates to work with)

    Returns:
        A dictionary containing both the seed tracks and recommended tracks
    """
    # First, check if the user is authenticated
    auth_check = requests.get(f"{FLASK_APP_URL}/api/auth/status")
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
        tracks_response = get_favorite_tracks(limit=limit_from_favorite)

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


@mcp.tool()
@requires_tidal_auth
def create_tidal_playlist(title: str, track_ids: list, description: str = "") -> TidalResponse:
    """
    Creates a new TIDAL playlist with the specified tracks.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Create a playlist with these songs"
    - "Make a TIDAL playlist"
    - "Save these tracks to a playlist"
    - "Create a collection of songs"
    - Any request to create a new playlist in their TIDAL account

    This function creates a new playlist in the user's TIDAL account and adds the specified tracks to it.
    The user must be authenticated with TIDAL first.

    NAMING CONVENTION GUIDANCE:
    When suggesting or creating a playlist, first check the user's existing playlists using get_user_playlists()
    to understand their naming preferences. Some patterns to look for:
    - Do they use emoji in playlist names?
    - Do they use all caps, title case, or lowercase?
    - Do they include dates or seasons in names?
    - Do they name by mood, genre, activity, or artist?
    - Do they use specific prefixes or formatting (e.g., "Mix: Summer Vibes" or "[Workout] High Energy")

    Try to match their style when suggesting new playlist names. If they have no playlists yet or you
    can't determine a pattern, use a clear, descriptive name based on the tracks' common themes.

    When processing the results of this tool:
    1. Confirm the playlist was created successfully
    2. Provide the playlist title, number of tracks added, and URL
    3. Always include the direct TIDAL URL (https://tidal.com/playlist/{playlist_id})
    4. Suggest that the user can now access this playlist in their TIDAL account

    Args:
        title: The name of the playlist to create
        track_ids: List of TIDAL track IDs to add to the playlist
        description: Optional description for the playlist (default: "")

    Returns:
        A dictionary containing the status of the playlist creation and details about the created playlist
    """
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

    result = make_tidal_request("/api/playlists", payload, method="POST")

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


@mcp.tool()
@requires_tidal_auth
def get_user_playlists() -> TidalResponse:
    """
    Fetches the user's playlists from their TIDAL account.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Show me my playlists"
    - "List my TIDAL playlists"
    - "What playlists do I have?"
    - "Get my music collections"
    - Any request to view or list their TIDAL playlists

    This function retrieves the user's playlists from TIDAL and returns them sorted
    by last updated date (most recent first).

    When processing the results of this tool:
    1. Present the playlists in a clear, organized format
    2. Include key information like title, track count, and the TIDAL URL for each playlist
    3. Mention when each playlist was last updated if available
    4. If the user has many playlists, focus on the most recently updated ones unless specified otherwise

    Returns:
        A dictionary containing the user's playlists sorted by last updated date
    """
    result = make_tidal_request("/api/playlists")

    if result["status"] != "success":
        return result

    playlists = result["data"].get("playlists", [])
    return {
        "status": "success",
        "playlists": playlists,
        "playlist_count": len(playlists)
    }


@mcp.tool()
@requires_tidal_auth
def get_playlist_tracks(playlist_id: str, limit: int = 100) -> TidalResponse:
    """
    Retrieves all tracks from a specified TIDAL playlist.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Show me the songs in my playlist"
    - "What tracks are in my [playlist name] playlist?"
    - "List the songs from my playlist"
    - "Get tracks from my playlist"
    - "View contents of my TIDAL playlist"
    - Any request to see what songs/tracks are in a specific playlist

    This function retrieves all tracks from a specific playlist in the user's TIDAL account.
    The playlist_id must be provided, which can be obtained from the get_user_playlists() function.

    When processing the results of this tool:
    1. Present the playlist information (title, description, track count) as context
    2. List the tracks in a clear, organized format with track name, artist, and album
    3. Include track durations where available
    4. Mention the total number of tracks in the playlist
    5. If there are many tracks, focus on highlighting interesting patterns or variety

    Args:
        playlist_id: The TIDAL ID of the playlist to retrieve (required)
        limit: Maximum number of tracks to retrieve (default: 100)

    Returns:
        A dictionary containing the playlist information and all tracks in the playlist
    """
    # Validate playlist_id
    if not playlist_id or not playlist_id.strip():
        return {
            "status": "error",
            "message": "A playlist ID is required. You can get playlist IDs by using the get_user_playlists() function."
        }

    params = {"limit": limit}
    result = make_tidal_request(f"/api/playlists/{playlist_id}/tracks", params)

    if result["status"] != "success":
        return result

    data = result["data"]
    return {
        "status": "success",
        "tracks": data.get("tracks", []),
        "track_count": data.get("total_tracks", 0)
    }


@mcp.tool()
@requires_tidal_auth
def delete_tidal_playlist(playlist_id: str) -> TidalResponse:
    """
    Deletes a TIDAL playlist by its ID.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Delete my playlist"
    - "Remove a playlist from my TIDAL account"
    - "Get rid of this playlist"
    - "Delete the playlist with ID X"
    - Any request to delete or remove a TIDAL playlist

    This function deletes a specific playlist from the user's TIDAL account.
    The user must be authenticated with TIDAL first.

    When processing the results of this tool:
    1. Confirm the playlist was deleted successfully
    2. Provide a clear message about the deletion

    Args:
        playlist_id: The TIDAL ID of the playlist to delete (required)

    Returns:
        A dictionary containing the status of the playlist deletion
    """
    # Validate playlist_id
    if not playlist_id or not playlist_id.strip():
        return {
            "status": "error",
            "message": "A playlist ID is required. You can get playlist IDs by using the get_user_playlists() function."
        }

    result = make_tidal_request(f"/api/playlists/{playlist_id}", method="DELETE")

    if result["status"] == "success":
        return result["data"]
    else:
        return result

@mcp.tool()
@requires_tidal_auth
def search_tidal(query: str, search_type: str = "all", limit: int = 20) -> SearchResults:
    """
    Search TIDAL for tracks, albums, artists, or playlists with comprehensive results.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Search for [song/artist/album] on TIDAL"
    - "Find songs by [artist]"
    - "Look for [song title]"
    - "Search TIDAL for [anything]"
    - Any general search request for music content

    This function provides comprehensive search across all TIDAL content types.

    When processing the results of this tool:
    1. Present search results in a clear, organized format by type (tracks, albums, artists, playlists)
    2. Include key information: track/album/artist name, duration, TIDAL URLs
    3. Highlight the most relevant results first
    4. If searching for specific content, focus on the most accurate matches
    5. Always include TIDAL URLs so users can easily access the content

    Args:
        query: The search term (song title, artist name, album name, etc.)
        search_type: Type of search - "all", "tracks", "albums", "artists", or "playlists" (default: "all")
        limit: Maximum number of results per type (default: 20)

    Returns:
        A dictionary containing search results organized by content type
    """
    # Validate inputs
    validation_error = validate_search_query(query)
    if validation_error:
        return validation_error

    if search_type not in VALID_SEARCH_TYPES:
        return {
            "status": "error",
            "message": f"Invalid search type '{search_type}'. Valid types: {', '.join(VALID_SEARCH_TYPES)}"
        }

    # Make the search request
    params = {
        "q": query.strip(),
        "type": search_type,
        "limit": limit
    }

    result = make_tidal_request("/api/search", params)

    if result["status"] != "success":
        return result

    data = result["data"]
    return {
        "status": "success",
        "query": query,
        "search_type": search_type,
        "limit": limit,
        "results": data.get("results", {}),
        "summary": data.get("summary", {})
    }


@mcp.tool()
@requires_tidal_auth
def search_tracks(query: str, limit: int = 20) -> SearchResults:
    """
    Search specifically for tracks/songs on TIDAL.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Find the song [title]"
    - "Search for tracks by [artist]"
    - "Look for [song title] by [artist]"
    - Any specific track/song search request

    This function searches specifically for tracks and returns detailed track information.

    Args:
        query: The search term (song title, artist name, or combination)
        limit: Maximum number of tracks to return (default: 20)

    Returns:
        A dictionary containing track search results with detailed information
    """
    validation_error = validate_search_query(query)
    if validation_error:
        return validation_error

    params = {"q": query.strip(), "limit": limit}
    result = make_tidal_request("/api/search/tracks", params)

    return format_search_results(query, "tracks", result, "tracks")


@mcp.tool()
@requires_tidal_auth
def search_albums(query: str, limit: int = 20) -> SearchResults:
    """
    Search specifically for albums on TIDAL.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Find the album [title]"
    - "Search for albums by [artist]"
    - "Look for [album name]"
    - Any specific album search request

    Args:
        query: The search term (album title, artist name, or combination)
        limit: Maximum number of albums to return (default: 20)

    Returns:
        A dictionary containing album search results with detailed information
    """
    validation_error = validate_search_query(query)
    if validation_error:
        return validation_error

    params = {"q": query.strip(), "limit": limit}
    result = make_tidal_request("/api/search/albums", params)

    return format_search_results(query, "albums", result, "albums")


@mcp.tool()
@requires_tidal_auth
def search_artists(query: str, limit: int = 20) -> SearchResults:
    """
    Search specifically for artists on TIDAL.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Find the artist [name]"
    - "Search for [artist name]"
    - "Look up [artist]"
    - Any specific artist search request

    Args:
        query: The search term (artist name)
        limit: Maximum number of artists to return (default: 20)

    Returns:
        A dictionary containing artist search results
    """
    validation_error = validate_search_query(query)
    if validation_error:
        return validation_error

    params = {"q": query.strip(), "limit": limit}
    result = make_tidal_request("/api/search/artists", params)

    return format_search_results(query, "artists", result, "artists")


@mcp.tool()
@requires_tidal_auth
def search_playlists(query: str, limit: int = 20) -> SearchResults:
    """
    Search specifically for playlists on TIDAL.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Find playlists about [topic]"
    - "Search for [playlist name]"
    - "Look for playlists with [genre/mood]"
    - Any playlist discovery request

    Args:
        query: The search term (playlist name, genre, mood, etc.)
        limit: Maximum number of playlists to return (default: 20)

    Returns:
        A dictionary containing playlist search results
    """
    validation_error = validate_search_query(query)
    if validation_error:
        return validation_error

    params = {"q": query.strip(), "limit": limit}
    result = make_tidal_request("/api/search/playlists", params)

    return format_search_results(query, "playlists", result, "playlists")
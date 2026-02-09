from mcp.server.fastmcp import FastMCP
import requests
import atexit
import functools
from typing import Optional, List, Dict, Any, Union

from mcp_server.utils import start_flask_app, shutdown_flask_app, FLASK_APP_URL, FLASK_PORT

# Import implementation functions
from mcp_server.tools.auth import tidal_login as tidal_login_impl
from mcp_server.tools.tracks import (
    get_favorite_tracks as get_favorite_tracks_impl,
    recommend_tracks as recommend_tracks_impl
)
from mcp_server.tools.playlists import (
    create_tidal_playlist as create_tidal_playlist_impl,
    get_user_playlists as get_user_playlists_impl,
    get_playlist_tracks as get_playlist_tracks_impl,
    delete_tidal_playlist as delete_tidal_playlist_impl,
    add_tracks_to_playlist as add_tracks_to_playlist_impl,
    remove_tracks_from_playlist as remove_tracks_from_playlist_impl,
    update_playlist_metadata as update_playlist_metadata_impl,
    reorder_playlist_tracks as reorder_playlist_tracks_impl
)
from mcp_server.tools.search import (
    search_tidal as search_tidal_impl,
    search_tracks as search_tracks_impl,
    search_albums as search_albums_impl,
    search_artists as search_artists_impl,
    search_playlists as search_playlists_impl
)

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
AUTH_ERROR_MESSAGE = "You need to login to TIDAL first before using this feature. Please use the tidal_login() function."

# Type aliases for better code clarity
TidalResponse = Dict[str, Any]
SearchResults = Dict[str, Union[str, int, List[Dict[str, Any]]]]


# =============================================================================
# HELPER FUNCTIONS & DECORATORS
# =============================================================================

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


def make_tidal_request(endpoint: str, params: Optional[Dict[str, Any]] = None, method: str = "GET") -> TidalResponse:
    """Make a request to the TIDAL API with standardized error handling."""
    try:
        url = f"{FLASK_APP_URL}{endpoint}"

        if method.upper() == "GET":
            response = requests.get(url, params=params, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(url, json=params, timeout=10)
        elif method.upper() == "PATCH":
            response = requests.patch(url, json=params, timeout=10)
        elif method.upper() == "DELETE":
            response = requests.delete(url, json=params, timeout=10)
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


# =============================================================================
# AUTHENTICATION TOOLS
# =============================================================================

@mcp.tool()
def tidal_login() -> dict:
    """
    Authenticate with TIDAL through browser login flow.
    This will open a browser window for the user to log in to their TIDAL account.

    Returns:
        A dictionary containing authentication status and user information if successful
    """
    return tidal_login_impl(FLASK_APP_URL)


# =============================================================================
# TRACK & RECOMMENDATION TOOLS
# =============================================================================

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
    return get_favorite_tracks_impl(FLASK_APP_URL, limit)


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
    # Pass get_favorite_tracks as a function reference to avoid circular dependencies
    return recommend_tracks_impl(
        FLASK_APP_URL,
        get_favorite_tracks,
        track_ids,
        filter_criteria,
        limit_per_track,
        limit_from_favorite
    )


# =============================================================================
# PLAYLIST MANAGEMENT TOOLS
# =============================================================================

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
    return create_tidal_playlist_impl(make_tidal_request, title, track_ids, description)


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
    return get_user_playlists_impl(make_tidal_request)


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
    return get_playlist_tracks_impl(make_tidal_request, playlist_id, limit)


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
    return delete_tidal_playlist_impl(make_tidal_request, playlist_id)


@mcp.tool()
@requires_tidal_auth
def add_tracks_to_playlist(playlist_id: str, track_ids: list) -> TidalResponse:
    """
    Add tracks to an existing TIDAL playlist.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Add these songs to my playlist"
    - "Add [track] to [playlist name]"
    - "Put these tracks in my playlist"
    - Any request to add songs/tracks to an existing playlist

    This function adds tracks to a user's existing TIDAL playlist. The playlist
    must already exist, and the user must have permission to edit it.

    When processing the results of this tool:
    1. Confirm how many tracks were added successfully
    2. Provide clear feedback about the operation
    3. If any tracks failed to add, explain why

    Args:
        playlist_id: The TIDAL ID of the playlist (required)
        track_ids: A list of TIDAL track IDs to add to the playlist (required)

    Returns:
        A dictionary containing the status of the operation and number of tracks added
    """
    return add_tracks_to_playlist_impl(make_tidal_request, playlist_id, track_ids)


@mcp.tool()
@requires_tidal_auth
def remove_tracks_from_playlist(playlist_id: str, track_ids: Optional[list] = None, indices: Optional[list] = None) -> TidalResponse:
    """
    Remove tracks from a TIDAL playlist by track IDs or position indices.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Remove this song from my playlist"
    - "Delete tracks from [playlist name]"
    - "Take out these songs from the playlist"
    - Any request to remove songs/tracks from a playlist

    This function removes specific tracks from a user's TIDAL playlist. You can remove
    tracks either by their TIDAL IDs or by their position in the playlist (0-based index).

    When processing the results of this tool:
    1. Confirm how many tracks were removed successfully
    2. Provide clear feedback about what was removed
    3. If using indices, remind the user they are 0-based (first track is index 0)

    Args:
        playlist_id: The TIDAL ID of the playlist (required)
        track_ids: A list of TIDAL track IDs to remove (optional - use this OR indices)
        indices: A list of track positions (0-based) to remove (optional - use this OR track_ids)

    Returns:
        A dictionary containing the status and number of tracks removed
    """
    return remove_tracks_from_playlist_impl(make_tidal_request, playlist_id, track_ids, indices)


@mcp.tool()
@requires_tidal_auth
def update_playlist_metadata(playlist_id: str, title: Optional[str] = None, description: Optional[str] = None) -> TidalResponse:
    """
    Update a TIDAL playlist's title and/or description.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Rename my playlist to [new name]"
    - "Change the playlist description"
    - "Update playlist [name] with new title/description"
    - Any request to modify playlist metadata

    This function updates the title and/or description of a user's TIDAL playlist.
    At least one of title or description must be provided.

    When processing the results of this tool:
    1. Confirm what was updated (title, description, or both)
    2. Show the new values
    3. Provide clear feedback that the changes were saved

    Args:
        playlist_id: The TIDAL ID of the playlist (required)
        title: New title for the playlist (optional)
        description: New description for the playlist (optional)

    Returns:
        A dictionary containing the status and updated fields
    """
    return update_playlist_metadata_impl(make_tidal_request, playlist_id, title, description)


@mcp.tool()
@requires_tidal_auth
def reorder_playlist_tracks(playlist_id: str, from_index: int, to_index: int) -> TidalResponse:
    """
    Move/reorder a track within a TIDAL playlist.

    USE THIS TOOL WHENEVER A USER ASKS FOR:
    - "Move track at position X to position Y"
    - "Reorder my playlist"
    - "Put song #5 at the beginning"
    - Any request to change the order of tracks in a playlist

    This function moves a track from one position to another within a playlist.
    Indices are 0-based (first track is index 0).

    When processing the results of this tool:
    1. Confirm the track was moved successfully
    2. Remind the user that indices are 0-based
    3. Describe the move clearly (e.g., "moved from position 5 to position 2")

    Args:
        playlist_id: The TIDAL ID of the playlist (required)
        from_index: Current position of the track (0-based) (required)
        to_index: New position for the track (0-based) (required)

    Returns:
        A dictionary containing the status of the move operation
    """
    return reorder_playlist_tracks_impl(make_tidal_request, playlist_id, from_index, to_index)


# =============================================================================
# SEARCH TOOLS
# =============================================================================

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
    return search_tidal_impl(make_tidal_request, query, search_type, limit)


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
    return search_tracks_impl(make_tidal_request, query, limit)


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
    return search_albums_impl(make_tidal_request, query, limit)


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
    return search_artists_impl(make_tidal_request, query, limit)


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
    return search_playlists_impl(make_tidal_request, query, limit)

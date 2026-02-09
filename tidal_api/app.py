import os
import tempfile
import functools

from flask import Flask, request, jsonify
from pathlib import Path

from tidal_api.browser_session import BrowserSession

# Import route implementation functions
from tidal_api.routes.auth import handle_login, check_auth_status
from tidal_api.routes.tracks import (
    get_user_tracks,
    get_single_track_recommendations,
    get_batch_track_recommendations
)
from tidal_api.routes.playlists import (
    create_new_playlist,
    get_playlists,
    get_tracks_from_playlist,
    delete_playlist_by_id,
    add_tracks,
    remove_tracks,
    update_playlist_metadata,
    move_track
)
from tidal_api.routes.search import (
    comprehensive_search,
    search_tracks_only,
    search_albums_only,
    search_artists_only,
    search_playlists_only
)

app = Flask(__name__)
token_path = os.path.join(tempfile.gettempdir(), 'tidal-session-oauth.json')
SESSION_FILE = Path(token_path)


def requires_tidal_auth(f):
    """
    Decorator to ensure routes have an authenticated TIDAL session.
    Returns 401 if not authenticated.
    Passes the authenticated session to the decorated function.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not SESSION_FILE.exists():
            return jsonify({"error": "Not authenticated"}), 401

        # Create session and load from file
        session = BrowserSession()
        login_success = session.login_session_file_auto(SESSION_FILE)

        if not login_success:
            return jsonify({"error": "Authentication failed"}), 401

        # Add the authenticated session to kwargs
        kwargs['session'] = session
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# AUTHENTICATION ROUTES
# =============================================================================

@app.route('/api/auth/login', methods=['GET'])
def login():
    """
    Initiates the TIDAL authentication process.
    Automatically opens a browser for the user to login to their TIDAL account.
    """
    def log_message(msg):
        print(f"TIDAL AUTH: {msg}")

    result, status_code = handle_login(SESSION_FILE, log_fn=log_message)
    return jsonify(result), status_code


@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """
    Check if there's an active authenticated session.
    """
    result, status_code = check_auth_status(SESSION_FILE)
    return jsonify(result), status_code


# =============================================================================
# TRACK & RECOMMENDATION ROUTES
# =============================================================================

@app.route('/api/tracks', methods=['GET'])
@requires_tidal_auth
def get_tracks(session: BrowserSession):
    """
    Get tracks from the user's history.
    """
    limit = request.args.get('limit', default=10, type=int)
    result, status_code = get_user_tracks(session, limit)
    return jsonify(result), status_code


@app.route('/api/recommendations/track/<track_id>', methods=['GET'])
@requires_tidal_auth
def get_track_recommendations(track_id: str, session: BrowserSession):
    """
    Get recommended tracks based on a specific track using TIDAL's track radio feature.
    """
    limit = request.args.get('limit', default=10, type=int)
    result, status_code = get_single_track_recommendations(session, track_id, limit)
    return jsonify(result), status_code


@app.route('/api/recommendations/batch', methods=['POST'])
@requires_tidal_auth
def get_batch_recommendations(session: BrowserSession):
    """
    Get recommended tracks based on a list of track IDs using concurrent requests.
    """
    request_data = request.get_json()
    if not request_data or 'track_ids' not in request_data:
        return jsonify({"error": "Missing track_ids in request body"}), 400

    track_ids = request_data['track_ids']
    limit_per_track = request_data.get('limit_per_track', 20)
    remove_duplicates = request_data.get('remove_duplicates', True)

    result, status_code = get_batch_track_recommendations(
        session,
        track_ids,
        limit_per_track,
        remove_duplicates
    )
    return jsonify(result), status_code


# =============================================================================
# PLAYLIST ROUTES
# =============================================================================

@app.route('/api/playlists', methods=['POST'])
@requires_tidal_auth
def create_playlist(session: BrowserSession):
    """
    Creates a new TIDAL playlist and adds tracks to it.

    Expected JSON payload:
    {
        "title": "Playlist title",
        "description": "Playlist description",
        "track_ids": [123456789, 987654321, ...]
    }

    Returns the created playlist information.
    """
    request_data = request.get_json()
    if not request_data:
        return jsonify({"error": "Missing request body"}), 400

    if 'title' not in request_data:
        return jsonify({"error": "Missing 'title' in request body"}), 400

    if 'track_ids' not in request_data or not request_data['track_ids']:
        return jsonify({"error": "Missing 'track_ids' in request body or empty track list"}), 400

    title = request_data['title']
    description = request_data.get('description', '')
    track_ids = request_data['track_ids']

    result, status_code = create_new_playlist(session, title, description, track_ids)
    return jsonify(result), status_code


@app.route('/api/playlists', methods=['GET'])
@requires_tidal_auth
def get_user_playlists(session: BrowserSession):
    """
    Get the user's playlists from TIDAL.
    """
    result, status_code = get_playlists(session)
    return jsonify(result), status_code


@app.route('/api/playlists/<playlist_id>/tracks', methods=['GET'])
@requires_tidal_auth
def get_playlist_tracks(playlist_id: str, session: BrowserSession):
    """
    Get tracks from a specific TIDAL playlist.
    By default, fetches ALL tracks using automatic pagination.
    """
    limit = request.args.get('limit', default=None, type=int)
    result, status_code = get_tracks_from_playlist(session, playlist_id, limit)
    return jsonify(result), status_code


@app.route('/api/playlists/<playlist_id>', methods=['DELETE'])
@requires_tidal_auth
def delete_playlist(playlist_id: str, session: BrowserSession):
    """
    Delete a TIDAL playlist by its ID.
    """
    result, status_code = delete_playlist_by_id(session, playlist_id)
    return jsonify(result), status_code


@app.route('/api/playlists/<playlist_id>/tracks', methods=['POST'])
@requires_tidal_auth
def add_tracks_to_playlist(playlist_id: str, session: BrowserSession):
    """
    Add tracks to an existing TIDAL playlist.

    Expected JSON payload:
    {
        "track_ids": [123456789, 987654321, ...]
    }
    """
    request_data = request.get_json()
    if not request_data:
        return jsonify({"error": "Missing request body"}), 400

    if 'track_ids' not in request_data or not request_data['track_ids']:
        return jsonify({"error": "Missing 'track_ids' in request body or empty track list"}), 400

    track_ids = request_data['track_ids']
    result, status_code = add_tracks(session, playlist_id, track_ids)
    return jsonify(result), status_code


@app.route('/api/playlists/<playlist_id>/tracks', methods=['DELETE'])
@requires_tidal_auth
def remove_tracks_from_playlist(playlist_id: str, session: BrowserSession):
    """
    Remove tracks from a TIDAL playlist.

    Expected JSON payload (one of):
    {
        "track_ids": [123456789, 987654321, ...]  // Remove by track ID
    }
    OR
    {
        "indices": [0, 5, 10, ...]  // Remove by position
    }
    """
    request_data = request.get_json()
    if not request_data:
        return jsonify({"error": "Missing request body"}), 400

    track_ids = request_data.get('track_ids')
    indices = request_data.get('indices')

    result, status_code = remove_tracks(
        session,
        playlist_id,
        track_ids,
        indices,
        logger=app.logger
    )
    return jsonify(result), status_code


@app.route('/api/playlists/<playlist_id>', methods=['PATCH'])
@requires_tidal_auth
def update_playlist(playlist_id: str, session: BrowserSession):
    """
    Update a TIDAL playlist's title and/or description.

    Expected JSON payload:
    {
        "title": "New playlist title",      // Optional
        "description": "New description"    // Optional
    }
    """
    request_data = request.get_json()
    if not request_data:
        return jsonify({"error": "Missing request body"}), 400

    title = request_data.get('title')
    description = request_data.get('description')

    result, status_code = update_playlist_metadata(session, playlist_id, title, description)
    return jsonify(result), status_code


@app.route('/api/playlists/<playlist_id>/tracks/move', methods=['POST'])
@requires_tidal_auth
def move_playlist_track(playlist_id: str, session: BrowserSession):
    """
    Move/reorder a track within a TIDAL playlist.

    Expected JSON payload:
    {
        "from_index": 5,    // Current position of the track (0-based)
        "to_index": 2       // New position for the track (0-based)
    }
    """
    request_data = request.get_json()
    if not request_data:
        return jsonify({"error": "Missing request body"}), 400

    if 'from_index' not in request_data or 'to_index' not in request_data:
        return jsonify({"error": "Must provide both 'from_index' and 'to_index'"}), 400

    from_index = request_data['from_index']
    to_index = request_data['to_index']

    result, status_code = move_track(session, playlist_id, from_index, to_index)
    return jsonify(result), status_code


# =============================================================================
# SEARCH ROUTES
# =============================================================================

@app.route('/api/search', methods=['GET'])
@requires_tidal_auth
def search(session: BrowserSession):
    """Enhanced search endpoint supporting comprehensive TIDAL search"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    search_type = request.args.get('type', 'all')
    limit = request.args.get('limit', default=50, type=int)

    result, status_code = comprehensive_search(
        session,
        query,
        search_type,
        limit,
        logger=app.logger
    )
    return jsonify(result), status_code


@app.route('/api/search/tracks', methods=['GET'])
@requires_tidal_auth
def search_tracks(session: BrowserSession):
    """Dedicated tracks search endpoint"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    limit = request.args.get('limit', default=50, type=int)

    result, status_code = search_tracks_only(session, query, limit, logger=app.logger)
    return jsonify(result), status_code


@app.route('/api/search/albums', methods=['GET'])
@requires_tidal_auth
def search_albums(session: BrowserSession):
    """Dedicated albums search endpoint"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    limit = request.args.get('limit', default=50, type=int)

    result, status_code = search_albums_only(session, query, limit, logger=app.logger)
    return jsonify(result), status_code


@app.route('/api/search/artists', methods=['GET'])
@requires_tidal_auth
def search_artists(session: BrowserSession):
    """Dedicated artists search endpoint"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    limit = request.args.get('limit', default=50, type=int)

    result, status_code = search_artists_only(session, query, limit, logger=app.logger)
    return jsonify(result), status_code


@app.route('/api/search/playlists', methods=['GET'])
@requires_tidal_auth
def search_playlists(session: BrowserSession):
    """Dedicated playlists search endpoint"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    limit = request.args.get('limit', default=50, type=int)

    result, status_code = search_playlists_only(session, query, limit, logger=app.logger)
    return jsonify(result), status_code


if __name__ == '__main__':
    # Get port from environment variable or use default
    port = int(os.environ.get("TIDAL_MCP_PORT", 5050))

    print(f"Starting Flask app on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)

import os
import tempfile
import functools

from flask import Flask, request, jsonify
from pathlib import Path

from tidal_api.browser_session import BrowserSession
from tidal_api.utils import format_track_data, bound_limit
import tidalapi

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


@app.route('/api/auth/login', methods=['GET'])
def login():
    """
    Initiates the TIDAL authentication process.
    Automatically opens a browser for the user to login to their TIDAL account.
    """
    # Create our custom session object
    session = BrowserSession()

    def log_message(msg):
        print(f"TIDAL AUTH: {msg}")

    # Try to authenticate (will open browser if needed)
    try:
        login_success = session.login_session_file_auto(SESSION_FILE, fn_print=log_message)

        if login_success:
            return jsonify({
                "status": "success",
                "message": "Successfully authenticated with TIDAL",
                "user_id": session.user.id
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Authentication failed"
            }), 401

    except TimeoutError:
        return jsonify({
            "status": "error",
            "message": "Authentication timed out"
        }), 408

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """
    Check if there's an active authenticated session.
    """
    if not SESSION_FILE.exists():
        return jsonify({
            "authenticated": False,
            "message": "No session file found"
        })

    # Create session and try to load from file
    session = BrowserSession()
    login_success = session.login_session_file_auto(SESSION_FILE)

    if login_success:
        # Get basic user info
        user_info = {
            "id": session.user.id,
            "username": session.user.username if hasattr(session.user, 'username') else "N/A",
            "email": session.user.email if hasattr(session.user, 'email') else "N/A"
        }

        return jsonify({
            "authenticated": True,
            "message": "Valid TIDAL session",
            "user": user_info
        })
    else:
        return jsonify({
            "authenticated": False,
            "message": "Invalid or expired session"
        })

@app.route('/api/tracks', methods=['GET'])
@requires_tidal_auth
def get_tracks(session: BrowserSession):
    """
    Get tracks from the user's history.
    """
    try:
        # TODO: Add streaminig history support if TIDAL API allows it
        # Get user favorites or history (for now limiting to user favorites only)
        favorites = session.user.favorites

        # Get limit from query parameter, default to 10 if not specified
        limit = bound_limit(request.args.get('limit', default=10, type=int))

        tracks = favorites.tracks(limit=limit, order="DATE", order_direction="DESC")
        track_list = [format_track_data(track) for track in tracks]

        return jsonify({"tracks": track_list})
    except Exception as e:
        return jsonify({"error": f"Error fetching tracks: {str(e)}"}), 500


@app.route('/api/recommendations/track/<track_id>', methods=['GET'])
@requires_tidal_auth
def get_track_recommendations(track_id: str, session: BrowserSession):
    """
    Get recommended tracks based on a specific track using TIDAL's track radio feature.
    """
    try:
        # Get limit from query parameter, default to 10 if not specified
        limit = bound_limit(request.args.get('limit', default=10, type=int))

        # Get recommendations using track radio
        track = session.track(track_id)
        if not track:
            return jsonify({"error": f"Track with ID {track_id} not found"}), 404

        recommendations = track.get_track_radio(limit=limit)

        # Format track data
        track_list = [format_track_data(track) for track in recommendations]
        return jsonify({"recommendations": track_list})
    except Exception as e:
        return jsonify({"error": f"Error fetching recommendations: {str(e)}"}), 500


@app.route('/api/recommendations/batch', methods=['POST'])
@requires_tidal_auth
def get_batch_recommendations(session: BrowserSession):
    """
    Get recommended tracks based on a list of track IDs using concurrent requests.
    """
    import concurrent.futures

    try:
        # Get request data
        request_data = request.get_json()
        if not request_data or 'track_ids' not in request_data:
            return jsonify({"error": "Missing track_ids in request body"}), 400

        track_ids = request_data['track_ids']
        if not isinstance(track_ids, list):
            return jsonify({"error": "track_ids must be a list"}), 400

        # Get limit per track from query parameter
        limit_per_track = bound_limit(request_data.get('limit_per_track', 20))

        # Optional parameter to remove duplicates across recommendations
        remove_duplicates = request_data.get('remove_duplicates', True)

        def get_track_recommendations(track_id):
            """Function to get recommendations for a single track"""
            try:
                track = session.track(track_id)
                recommendations = track.get_track_radio(limit=limit_per_track)
                # Format track data immediately
                formatted_recommendations = [
                    format_track_data(rec, source_track_id=track_id)
                    for rec in recommendations
                ]
                return formatted_recommendations
            except Exception as e:
                print(f"Error getting recommendations for track {track_id}: {str(e)}")
                return []

        all_recommendations = []
        seen_track_ids = set()

        # Use ThreadPoolExecutor to process tracks concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(track_ids)) as executor:
            # Submit all tasks and map them to their track_ids
            future_to_track_id = {
                executor.submit(get_track_recommendations, track_id): track_id
                for track_id in track_ids
            }

            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_track_id):
                track_recommendations = future.result()

                # Add recommendations to the result list
                for track_data in track_recommendations:
                    track_id = track_data.get('id')

                    # Skip if we've already seen this track and want to remove duplicates
                    if remove_duplicates and track_id in seen_track_ids:
                        continue

                    all_recommendations.append(track_data)
                    seen_track_ids.add(track_id)

        return jsonify({"recommendations": all_recommendations})
    except Exception as e:
        return jsonify({"error": f"Error fetching batch recommendations: {str(e)}"}), 500


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
    try:
        # Get request data
        request_data = request.get_json()
        if not request_data:
            return jsonify({"error": "Missing request body"}), 400

        # Validate required fields
        if 'title' not in request_data:
            return jsonify({"error": "Missing 'title' in request body"}), 400

        if 'track_ids' not in request_data or not request_data['track_ids']:
            return jsonify({"error": "Missing 'track_ids' in request body or empty track list"}), 400

        # Get parameters from request
        title = request_data['title']
        description = request_data.get('description', '')  # Optional
        track_ids = request_data['track_ids']

        # Validate track_ids is a list
        if not isinstance(track_ids, list):
            return jsonify({"error": "'track_ids' must be a list"}), 400

        # Create the playlist
        playlist = session.user.create_playlist(title, description)

        # Add tracks to the playlist
        playlist.add(track_ids)

        # Return playlist information
        playlist_info = {
            "id": playlist.id,
            "title": playlist.name,
            "description": playlist.description,
            "created": playlist.created,
            "last_updated": playlist.last_updated,
            "track_count": playlist.num_tracks,
            "duration": playlist.duration,
        }

        return jsonify({
            "status": "success",
            "message": f"Playlist '{title}' created successfully with {len(track_ids)} tracks",
            "playlist": playlist_info
        })

    except Exception as e:
        return jsonify({"error": f"Error creating playlist: {str(e)}"}), 500


@app.route('/api/playlists', methods=['GET'])
@requires_tidal_auth
def get_user_playlists(session: BrowserSession):
    """
    Get the user's playlists from TIDAL.
    """
    try:
        # Get user playlists
        playlists = session.user.playlists()

        # Format playlist data
        playlist_list = []
        for playlist in playlists:
            playlist_info = {
                "id": playlist.id,
                "title": playlist.name,
                "description": playlist.description if hasattr(playlist, 'description') else "",
                "created": playlist.created if hasattr(playlist, 'created') else None,
                "last_updated": playlist.last_updated if hasattr(playlist, 'last_updated') else None,
                "track_count": playlist.num_tracks if hasattr(playlist, 'num_tracks') else 0,
                "duration": playlist.duration if hasattr(playlist, 'duration') else 0,
                "url": f"https://tidal.com/playlist/{playlist.id}"
            }
            playlist_list.append(playlist_info)

        # Sort playlists by last_updated in descending order
        sorted_playlists = sorted(
            playlist_list,
            key=lambda x: x.get('last_updated', ''),
            reverse=True
        )

        return jsonify({"playlists": sorted_playlists})
    except Exception as e:
        return jsonify({"error": f"Error fetching playlists: {str(e)}"}), 500


@app.route('/api/playlists/<playlist_id>/tracks', methods=['GET'])
@requires_tidal_auth
def get_playlist_tracks(playlist_id: str, session: BrowserSession):
    """
    Get tracks from a specific TIDAL playlist.
    """
    try:
        # Get limit from query parameter, default to 100 if not specified
        limit = bound_limit(request.args.get('limit', default=100, type=int))

        # Get the playlist object
        playlist = session.playlist(playlist_id)
        if not playlist:
            return jsonify({"error": f"Playlist with ID {playlist_id} not found"}), 404

        # Get tracks from the playlist with pagination if needed
        tracks = playlist.items(limit=limit)

        # Format track data
        track_list = [format_track_data(track) for track in tracks]

        return jsonify({
            "playlist_id": playlist.id,
            "tracks": track_list,
            "total_tracks": len(track_list)
        })

    except Exception as e:
        return jsonify({"error": f"Error fetching playlist tracks: {str(e)}"}), 500


@app.route('/api/playlists/<playlist_id>', methods=['DELETE'])
@requires_tidal_auth
def delete_playlist(playlist_id: str, session: BrowserSession):
    """
    Delete a TIDAL playlist by its ID.
    """
    try:
        # Get the playlist object
        playlist = session.playlist(playlist_id)
        if not playlist:
            return jsonify({"error": f"Playlist with ID {playlist_id} not found"}), 404


        # Delete the playlist
        playlist.delete()


        return jsonify({
            "status": "success",
            "message": f"Playlist with ID {playlist_id} was successfully deleted"
        })


    except Exception as e:
        return jsonify({"error": f"Error deleting playlist: {str(e)}"}), 500


@app.route('/api/search', methods=['GET'])
@requires_tidal_auth
def search(session: BrowserSession):
    """Enhanced search endpoint supporting comprehensive TIDAL search"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    # Search parameters
    search_type = request.args.get('type', 'all')  # all, tracks, albums, artists, playlists
    limit = bound_limit(request.args.get('limit', default=50, type=int))

    try:
        if not session.check_login():
            return jsonify({"error": "Not authenticated with TIDAL"}), 401

        results = {}

        if search_type == 'all' or search_type == 'tracks':
            # Search for tracks
            track_results = session.search(query, limit=limit)
            app.logger.info(f"Track search results type: {type(track_results)}")

            tracks = []
            if hasattr(track_results, 'tracks') and track_results.tracks:
                tracks = track_results.tracks
            elif isinstance(track_results, dict) and 'tracks' in track_results:
                tracks = track_results['tracks']
            elif isinstance(track_results, list):
                tracks = track_results

            if tracks:
                results['tracks'] = {
                    'items': [format_track_data(track) for track in tracks[:limit]],
                    'total': len(tracks[:limit])
                }

        if search_type == 'all' or search_type == 'albums':
            # Search for albums
            album_results = session.search(query, limit=limit)
            app.logger.info(f"Album search results type: {type(album_results)}")

            albums = []
            if hasattr(album_results, 'albums') and album_results.albums:
                albums = album_results.albums
            elif isinstance(album_results, dict) and 'albums' in album_results:
                albums = album_results['albums']

            if albums:
                formatted_albums = []
                for album in albums[:limit]:
                    album_data = {
                        "id": album.id,
                        "title": album.name,
                        "artist": album.artist.name if album.artist else "Unknown Artist",
                        "release_date": str(album.release_date) if hasattr(album, 'release_date') and album.release_date else None,
                        "num_tracks": album.num_tracks if hasattr(album, 'num_tracks') else 0,
                        "duration": album.duration if hasattr(album, 'duration') else 0,
                        "explicit": album.explicit if hasattr(album, 'explicit') else False,
                        "url": f"https://tidal.com/browse/album/{album.id}?u"
                    }
                    formatted_albums.append(album_data)
                results['albums'] = {
                    'items': formatted_albums,
                    'total': len(formatted_albums)
                }

        if search_type == 'all' or search_type == 'artists':
            # Search for artists
            artist_results = session.search(query, limit=limit)
            app.logger.info(f"Artist search results type: {type(artist_results)}")

            artists = []
            if hasattr(artist_results, 'artists') and artist_results.artists:
                artists = artist_results.artists
            elif isinstance(artist_results, dict) and 'artists' in artist_results:
                artists = artist_results['artists']

            if artists:
                formatted_artists = []
                for artist in artists[:limit]:
                    artist_data = {
                        "id": artist.id,
                        "name": artist.name,
                        "url": f"https://tidal.com/browse/artist/{artist.id}?u"
                    }
                    formatted_artists.append(artist_data)
                results['artists'] = {
                    'items': formatted_artists,
                    'total': len(formatted_artists)
                }

        if search_type == 'all' or search_type == 'playlists':
            # Search for playlists
            playlist_results = session.search(query, limit=limit)
            app.logger.info(f"Playlist search results type: {type(playlist_results)}")

            playlists = []
            if hasattr(playlist_results, 'playlists') and playlist_results.playlists:
                playlists = playlist_results.playlists
            elif isinstance(playlist_results, dict) and 'playlists' in playlist_results:
                playlists = playlist_results['playlists']

            if playlists:
                formatted_playlists = []
                for playlist in playlists[:limit]:
                    playlist_data = {
                        "id": playlist.id,
                        "title": playlist.name,
                        "description": playlist.description if hasattr(playlist, 'description') else None,
                        "creator": playlist.creator.name if hasattr(playlist, 'creator') and playlist.creator else "Unknown",
                        "num_tracks": playlist.num_tracks if hasattr(playlist, 'num_tracks') else 0,
                        "duration": playlist.duration if hasattr(playlist, 'duration') else 0,
                        "url": f"https://tidal.com/browse/playlist/{playlist.id}?u"
                    }
                    formatted_playlists.append(playlist_data)
                results['playlists'] = {
                    'items': formatted_playlists,
                    'total': len(formatted_playlists)
                }

        # Create summary
        summary = {}
        for result_type, data in results.items():
            if 'total' in data:
                summary[result_type] = data['total']

        return jsonify({
            "query": query,
            "searchType": search_type,
            "limit": limit,
            "results": results,
            "summary": summary
        })

    except Exception as e:
        app.logger.error(f"Search error: {str(e)}")
        import traceback
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Search failed: {str(e)}"}), 500

@app.route('/api/search/tracks', methods=['GET'])
@requires_tidal_auth
def search_tracks(session: BrowserSession):
    """Dedicated tracks search endpoint"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    limit = bound_limit(request.args.get('limit', default=50, type=int))

    try:
        if not session.check_login():
            return jsonify({"error": "Not authenticated with TIDAL"}), 401

        # Try different search approaches
        app.logger.info(f"Searching for tracks: '{query}' with limit {limit}")

        # Try the basic search first
        results = session.search(query, limit=limit)
        app.logger.info(f"Search results type: {type(results)}")
        app.logger.info(f"Search results: {results}")

        # Check if results is a dict or has tracks attribute
        if hasattr(results, 'tracks') and results.tracks:
            app.logger.info(f"Found {len(results.tracks)} tracks via .tracks attribute")
            formatted_results = [format_track_data(track) for track in results.tracks]
        elif isinstance(results, dict) and 'tracks' in results:
            app.logger.info(f"Found {len(results['tracks'])} tracks via dict key")
            formatted_results = [format_track_data(track) for track in results['tracks']]
        elif isinstance(results, list):
            app.logger.info(f"Results is a list with {len(results)} items")
            # Assume it's a list of tracks
            formatted_results = [format_track_data(track) for track in results]
        else:
            app.logger.warning(f"Unexpected results format: {type(results)}")
            # Try with specific models parameter
            results = session.search(query, models=[tidalapi.Track], limit=limit)
            app.logger.info(f"Search with models results type: {type(results)}")

            if hasattr(results, 'tracks') and results.tracks:
                formatted_results = [format_track_data(track) for track in results.tracks]
            elif isinstance(results, dict) and 'tracks' in results:
                formatted_results = [format_track_data(track) for track in results['tracks']]
            elif isinstance(results, list):
                formatted_results = [format_track_data(track) for track in results]
            else:
                return jsonify({
                    "query": query,
                    "type": "tracks",
                    "limit": limit,
                    "results": {"tracks": {"items": [], "total": 0}},
                    "count": 0,
                    "debug": f"No tracks found. Results type: {type(results)}, content: {str(results)[:200]}"
                })

        return jsonify({
            "query": query,
            "type": "tracks",
            "limit": limit,
            "results": {
                "tracks": {
                    "items": formatted_results,
                    "total": len(formatted_results)
                }
            },
            "count": len(formatted_results)
        })

    except Exception as e:
        app.logger.error(f"Track search error: {str(e)}")
        import traceback
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Track search failed: {str(e)}"}), 500

@app.route('/api/search/albums', methods=['GET'])
@requires_tidal_auth
def search_albums(session: BrowserSession):
    """Dedicated albums search endpoint"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    limit = bound_limit(request.args.get('limit', default=50, type=int))

    try:
        if not session.check_login():
            return jsonify({"error": "Not authenticated with TIDAL"}), 401

        results = session.search(query, models=[tidalapi.Album], limit=limit)

        if results and results.albums:
            formatted_results = []
            for album in results.albums:
                album_data = {
                    "id": album.id,
                    "title": album.name,
                    "artist": album.artist.name if album.artist else "Unknown Artist",
                    "release_date": str(album.release_date) if hasattr(album, 'release_date') and album.release_date else None,
                    "num_tracks": album.num_tracks if hasattr(album, 'num_tracks') else 0,
                    "duration": album.duration if hasattr(album, 'duration') else 0,
                    "explicit": album.explicit if hasattr(album, 'explicit') else False,
                    "url": f"https://tidal.com/browse/album/{album.id}?u"
                }
                formatted_results.append(album_data)

            return jsonify({
                "query": query,
                "type": "albums",
                "limit": limit,
                "results": {
                    "albums": {
                        "items": formatted_results,
                        "total": len(formatted_results)
                    }
                },
                "count": len(formatted_results)
            })
        else:
            return jsonify({
                "query": query,
                "type": "albums",
                "limit": limit,
                "results": {"albums": {"items": [], "total": 0}},
                "count": 0
            })

    except Exception as e:
        app.logger.error(f"Album search error: {str(e)}")
        return jsonify({"error": f"Album search failed: {str(e)}"}), 500

@app.route('/api/search/artists', methods=['GET'])
@requires_tidal_auth
def search_artists(session: BrowserSession):
    """Dedicated artists search endpoint"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    limit = bound_limit(request.args.get('limit', default=50, type=int))

    try:
        if not session.check_login():
            return jsonify({"error": "Not authenticated with TIDAL"}), 401

        results = session.search(query, models=[tidalapi.Artist], limit=limit)

        if results and results.artists:
            formatted_results = []
            for artist in results.artists:
                artist_data = {
                    "id": artist.id,
                    "name": artist.name,
                    "url": f"https://tidal.com/browse/artist/{artist.id}?u"
                }
                formatted_results.append(artist_data)

            return jsonify({
                "query": query,
                "type": "artists",
                "limit": limit,
                "results": {
                    "artists": {
                        "items": formatted_results,
                        "total": len(formatted_results)
                    }
                },
                "count": len(formatted_results)
            })
        else:
            return jsonify({
                "query": query,
                "type": "artists",
                "limit": limit,
                "results": {"artists": {"items": [], "total": 0}},
                "count": 0
            })

    except Exception as e:
        app.logger.error(f"Artist search error: {str(e)}")
        return jsonify({"error": f"Artist search failed: {str(e)}"}), 500

@app.route('/api/search/playlists', methods=['GET'])
@requires_tidal_auth
def search_playlists(session: BrowserSession):
    """Dedicated playlists search endpoint"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    limit = bound_limit(request.args.get('limit', default=50, type=int))

    try:
        if not session.check_login():
            return jsonify({"error": "Not authenticated with TIDAL"}), 401

        results = session.search(query, models=[tidalapi.Playlist], limit=limit)

        if results and results.playlists:
            formatted_results = []
            for playlist in results.playlists:
                playlist_data = {
                    "id": playlist.id,
                    "title": playlist.name,
                    "description": playlist.description if hasattr(playlist, 'description') else None,
                    "creator": playlist.creator.name if hasattr(playlist, 'creator') and playlist.creator else "Unknown",
                    "num_tracks": playlist.num_tracks if hasattr(playlist, 'num_tracks') else 0,
                    "duration": playlist.duration if hasattr(playlist, 'duration') else 0,
                    "url": f"https://tidal.com/browse/playlist/{playlist.id}?u"
                }
                formatted_results.append(playlist_data)

            return jsonify({
                "query": query,
                "type": "playlists",
                "limit": limit,
                "results": {
                    "playlists": {
                        "items": formatted_results,
                        "total": len(formatted_results)
                    }
                },
                "count": len(formatted_results)
            })
        else:
            return jsonify({
                "query": query,
                "type": "playlists",
                "limit": limit,
                "results": {"playlists": {"items": [], "total": 0}},
                "count": 0
            })

    except Exception as e:
        app.logger.error(f"Playlist search error: {str(e)}")
        return jsonify({"error": f"Playlist search failed: {str(e)}"}), 500

def search_with_type(search_type, session):
    """Helper function for type-specific searches - DEPRECATED, use individual endpoints"""
    pass



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
    try:
        # Get request data
        request_data = request.get_json()
        if not request_data:
            return jsonify({"error": "Missing request body"}), 400

        # Validate required fields
        if 'track_ids' not in request_data or not request_data['track_ids']:
            return jsonify({"error": "Missing 'track_ids' in request body or empty track list"}), 400

        track_ids = request_data['track_ids']

        # Validate track_ids is a list
        if not isinstance(track_ids, list):
            return jsonify({"error": "'track_ids' must be a list"}), 400

        # Get the playlist object
        playlist = session.playlist(playlist_id)
        if not playlist:
            return jsonify({"error": f"Playlist with ID {playlist_id} not found"}), 404

        # Add tracks to the playlist
        playlist.add(track_ids)

        return jsonify({
            "status": "success",
            "message": f"Added {len(track_ids)} track(s) to playlist",
            "playlist_id": playlist_id,
            "tracks_added": len(track_ids)
        })

    except Exception as e:
        return jsonify({"error": f"Error adding tracks to playlist: {str(e)}"}), 500


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
    try:
        # Get request data
        request_data = request.get_json()
        if not request_data:
            return jsonify({"error": "Missing request body"}), 400

        # Get the playlist object
        playlist = session.playlist(playlist_id)
        if not playlist:
            return jsonify({"error": f"Playlist with ID {playlist_id} not found"}), 404

        removed_count = 0

        # Remove by track IDs
        if 'track_ids' in request_data:
            track_ids = request_data['track_ids']
            if not isinstance(track_ids, list):
                return jsonify({"error": "'track_ids' must be a list"}), 400

            for track_id in track_ids:
                try:
                    playlist.remove_by_id(track_id)
                    removed_count += 1
                except Exception as e:
                    app.logger.warning(f"Could not remove track {track_id}: {str(e)}")

        # Remove by indices
        elif 'indices' in request_data:
            indices = request_data['indices']
            if not isinstance(indices, list):
                return jsonify({"error": "'indices' must be a list"}), 400

            # Sort indices in descending order to avoid shifting issues
            for index in sorted(indices, reverse=True):
                try:
                    playlist.remove_by_index(index)
                    removed_count += 1
                except Exception as e:
                    app.logger.warning(f"Could not remove track at index {index}: {str(e)}")
        else:
            return jsonify({"error": "Must provide either 'track_ids' or 'indices'"}), 400

        return jsonify({
            "status": "success",
            "message": f"Removed {removed_count} track(s) from playlist",
            "playlist_id": playlist_id,
            "tracks_removed": removed_count
        })

    except Exception as e:
        return jsonify({"error": f"Error removing tracks from playlist: {str(e)}"}), 500


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
    try:
        # Get request data
        request_data = request.get_json()
        if not request_data:
            return jsonify({"error": "Missing request body"}), 400

        title = request_data.get('title')
        description = request_data.get('description')

        if not title and not description:
            return jsonify({"error": "Must provide at least 'title' or 'description'"}), 400

        # Get the playlist object
        playlist = session.playlist(playlist_id)
        if not playlist:
            return jsonify({"error": f"Playlist with ID {playlist_id} not found"}), 404

        # Update the playlist metadata
        playlist.edit(title=title, description=description)

        return jsonify({
            "status": "success",
            "message": "Playlist updated successfully",
            "playlist_id": playlist_id,
            "updated_fields": {
                "title": title if title else playlist.name,
                "description": description if description else playlist.description
            }
        })

    except Exception as e:
        return jsonify({"error": f"Error updating playlist: {str(e)}"}), 500


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
    try:
        # Get request data
        request_data = request.get_json()
        if not request_data:
            return jsonify({"error": "Missing request body"}), 400

        if 'from_index' not in request_data or 'to_index' not in request_data:
            return jsonify({"error": "Must provide both 'from_index' and 'to_index'"}), 400

        from_index = request_data['from_index']
        to_index = request_data['to_index']

        # Validate indices are integers
        if not isinstance(from_index, int) or not isinstance(to_index, int):
            return jsonify({"error": "'from_index' and 'to_index' must be integers"}), 400

        if from_index < 0 or to_index < 0:
            return jsonify({"error": "Indices must be non-negative"}), 400

        # Get the playlist object
        playlist = session.playlist(playlist_id)
        if not playlist:
            return jsonify({"error": f"Playlist with ID {playlist_id} not found"}), 404

        # Move the track
        playlist.move(from_index, to_index)

        return jsonify({
            "status": "success",
            "message": f"Moved track from position {from_index} to {to_index}",
            "playlist_id": playlist_id,
            "from_index": from_index,
            "to_index": to_index
        })

    except Exception as e:
        return jsonify({"error": f"Error moving track in playlist: {str(e)}"}), 500


if __name__ == '__main__':
    import os

    # Get port from environment variable or use default
    port = int(os.environ.get("TIDAL_MCP_PORT", 5050))

    print(f"Starting Flask app on port {port}")
    app.run(debug=True, port=port)
"""TIDAL algorithmic mixes route implementation logic."""
from tidal_api.browser_session import BrowserSession
from tidal_api.utils import format_track_data


def get_user_mixes(session: BrowserSession) -> tuple:
    """Get the user's TIDAL algorithmic mixes (My Daily Discovery, New Arrivals, etc.)."""
    try:
        mix_list = []
        mixes = session.mixes()  # tidalapi >=0.8.x: returns a Page of Mix objects
        for mix in mixes:
            mix_list.append({
                "id": str(mix.id),
                "title": mix.title if hasattr(mix, 'title') else str(mix.id),
                "sub_title": getattr(mix, 'sub_title', ''),
                "track_count": getattr(mix, 'number_of_tracks', 0) or 0,
            })
        return {"mixes": mix_list}, 200
    except Exception as e:
        # Mixes are best-effort; never fail the caller, just report the warning.
        return {"mixes": [], "warning": f"Could not fetch mixes: {str(e)}"}, 200


def get_mix_tracks(session: BrowserSession, mix_id: str, limit: int = 100) -> tuple:
    """Get tracks from a specific TIDAL mix."""
    try:
        limit = max(1, min(500, limit))
        mix = session.mix(mix_id)
        all_tracks = mix.items()
        track_list = [format_track_data(track) for track in all_tracks[:limit]]
        return {"mix_id": mix_id, "tracks": track_list, "count": len(track_list)}, 200
    except Exception as e:
        return {"error": f"Error fetching mix tracks: {str(e)}"}, 500

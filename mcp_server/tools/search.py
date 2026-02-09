"""Search implementation logic."""
from typing import Dict, Any, Optional, Union, List

# Constants
VALID_SEARCH_TYPES = ["all", "tracks", "albums", "artists", "playlists"]
EMPTY_QUERY_ERROR = "Search query cannot be empty. Please provide a search term."

# Type aliases
TidalResponse = Dict[str, Any]
SearchResults = Dict[str, Union[str, int, List[Dict[str, Any]]]]


def validate_search_query(query: str) -> Optional[TidalResponse]:
    """Validate search query input. Returns error dict if invalid, None if valid."""
    if not query or not query.strip():
        return {
            "status": "error",
            "message": EMPTY_QUERY_ERROR
        }
    return None


def format_search_results(
    query: str,
    result_type: str,
    data: TidalResponse,
    extract_key: str
) -> SearchResults:
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


def search_tidal(
    make_tidal_request_func,
    query: str,
    search_type: str = "all",
    limit: int = 20
) -> SearchResults:
    """Implementation logic for comprehensive TIDAL search."""
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

    result = make_tidal_request_func("/api/search", params)

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


def search_tracks(
    make_tidal_request_func,
    query: str,
    limit: int = 20
) -> SearchResults:
    """Implementation logic for track search."""
    validation_error = validate_search_query(query)
    if validation_error:
        return validation_error

    params = {"q": query.strip(), "limit": limit}
    result = make_tidal_request_func("/api/search/tracks", params)

    return format_search_results(query, "tracks", result, "tracks")


def search_albums(
    make_tidal_request_func,
    query: str,
    limit: int = 20
) -> SearchResults:
    """Implementation logic for album search."""
    validation_error = validate_search_query(query)
    if validation_error:
        return validation_error

    params = {"q": query.strip(), "limit": limit}
    result = make_tidal_request_func("/api/search/albums", params)

    return format_search_results(query, "albums", result, "albums")


def search_artists(
    make_tidal_request_func,
    query: str,
    limit: int = 20
) -> SearchResults:
    """Implementation logic for artist search."""
    validation_error = validate_search_query(query)
    if validation_error:
        return validation_error

    params = {"q": query.strip(), "limit": limit}
    result = make_tidal_request_func("/api/search/artists", params)

    return format_search_results(query, "artists", result, "artists")


def search_playlists(
    make_tidal_request_func,
    query: str,
    limit: int = 20
) -> SearchResults:
    """Implementation logic for playlist search."""
    validation_error = validate_search_query(query)
    if validation_error:
        return validation_error

    params = {"q": query.strip(), "limit": limit}
    result = make_tidal_request_func("/api/search/playlists", params)

    return format_search_results(query, "playlists", result, "playlists")

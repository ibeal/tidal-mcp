"""Listening-history surfaces (HISTORY_* mixes) from TIDAL's raw home feed.

TIDAL tracks listening server-side and exposes it as history mixes
(HISTORY_ALLTIME_MIX / HISTORY_MONTHLY_MIX / HISTORY_YEARLY_MIX) on the
`home/feed/static` page. tidalapi's *typed* page parser drops these module types
(they're keyed by item `type`, not the `mix_type` attribute, so session.mixes() /
session.home() miss them). We therefore read the raw feed JSON and detect them by
`type`.

This is the native, source-of-truth proxy for "played a lot / played recently":
cross-referencing the mixes (membership + multiplicity + recency order) reconstructs
a frecency signal without any raw play counts. Tracks per mix are fetched separately
via /api/mixes/<id>/tracks.
"""
from tidal_api.browser_session import BrowserSession

# Item `type` -> our tier label.
HISTORY_TIER_BY_TYPE = {
    "HISTORY_ALLTIME_MIX": "alltime",
    "HISTORY_YEARLY_MIX": "yearly",
    "HISTORY_MONTHLY_MIX": "monthly",
}


def _iter_dicts(obj):
    """Depth-first walk yielding every dict in a nested JSON structure, in order."""
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item)


def get_listening_history(session: BrowserSession) -> tuple:
    """Return the user's HISTORY_* mixes with tier + recency order.

    Response shape:
        {
          "history_mixes": [
            {"id": "...", "tier": "alltime", "type": "HISTORY_ALLTIME_MIX",
             "month_index": null, "title": null},
            {"id": "...", "tier": "monthly", "month_index": 0, ...},  # 0 = most recent month
            ...
          ]
        }

    Best-effort: never raises to the caller (history is an optional enrichment).
    """
    try:
        feed = session.request.request(
            "GET",
            "home/feed/static",
            base_url=session.config.api_v2_location,
            params={
                "deviceType": "BROWSER",
                "locale": session.locale,
                "platform": "WEB",
            },
        ).json()
    except Exception as e:
        return {"history_mixes": [], "warning": f"Could not fetch home feed: {str(e)}"}, 200

    history_mixes = []
    seen = set()
    # Monthly mixes appear newest-first in the feed; index them so callers can apply
    # a recency decay (0 = most recent month). Assigned in document order.
    month_index = 0

    for node in _iter_dicts(feed):
        tier = HISTORY_TIER_BY_TYPE.get(node.get("type"))
        if not tier:
            continue
        mix_id = node.get("id")
        if not mix_id or mix_id in seen:
            continue
        seen.add(mix_id)

        entry = {
            "id": str(mix_id),
            "tier": tier,
            "type": node.get("type"),
            # title/sub_title are usually null in the feed; the full Mix object
            # (session.mix(id)) carries the real month label if ever needed.
            "title": node.get("title"),
            "month_index": None,
        }
        if tier == "monthly":
            entry["month_index"] = month_index
            month_index += 1
        history_mixes.append(entry)

    return {"history_mixes": history_mixes}, 200

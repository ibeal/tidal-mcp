"""Authentication route implementation logic."""
import threading
from pathlib import Path
from typing import Any, Optional

from tidal_api.browser_session import BrowserSession


_PENDING_LOCK = threading.Lock()
_PENDING_LOGIN: Optional[dict] = None  # {"session", "login", "future"}


def _clear_pending() -> None:
    global _PENDING_LOGIN
    _PENDING_LOGIN = None


def _format_auth_url(login: Any) -> str:
    auth_url = login.verification_uri_complete
    if not auth_url.startswith("http"):
        auth_url = "https://" + auth_url
    return auth_url


def handle_login(session_file: Path) -> tuple[dict, int]:
    """Non-blocking OAuth login handler.

    Returns one of:
      - 200 status="success" when a valid session exists (cached or just completed).
      - 202 status="pending" with verification_url while waiting for the user
        to complete OAuth in their browser.
      - 4xx/5xx status="error" on failure.

    State is stored in process memory across calls, so the MCP tool can poll
    by re-invoking the same endpoint.
    """
    global _PENDING_LOGIN

    with _PENDING_LOCK:
        if session_file.exists():
            session = BrowserSession()
            session.load_session_from_file(session_file)
            if session.check_login():
                _clear_pending()
                return {
                    "status": "success",
                    "message": "Already authenticated with TIDAL",
                    "user_id": session.user.id,
                }, 200

        if _PENDING_LOGIN is not None:
            session = _PENDING_LOGIN["session"]
            login = _PENDING_LOGIN["login"]
            future = _PENDING_LOGIN["future"]

            if future.done():
                try:
                    future.result(timeout=0)
                except TimeoutError:
                    _clear_pending()
                    return {
                        "status": "error",
                        "message": "Authentication timed out. Call tidal_login() again to restart.",
                    }, 408
                except Exception as e:
                    _clear_pending()
                    return {
                        "status": "error",
                        "message": f"Authentication failed: {e}",
                    }, 500

                if session.check_login():
                    session.save_session_to_file(session_file)
                    user_id = session.user.id
                    _clear_pending()
                    return {
                        "status": "success",
                        "message": "Successfully authenticated with TIDAL",
                        "user_id": user_id,
                    }, 200

                _clear_pending()
                return {
                    "status": "error",
                    "message": "OAuth completed but session is invalid. Call tidal_login() again to retry.",
                }, 401

            return {
                "status": "pending",
                "message": (
                    "Waiting for the user to complete browser login. "
                    "Show them the verification_url, then call tidal_login() again to check status."
                ),
                "verification_url": _format_auth_url(login),
                "expires_in": login.expires_in,
            }, 202

        session = BrowserSession()
        login, future = session.login_oauth()
        _PENDING_LOGIN = {
            "session": session,
            "login": login,
            "future": future,
        }

        return {
            "status": "pending",
            "message": (
                "Open the verification_url in a browser to log in to TIDAL, "
                "then call tidal_login() again to finalize the session."
            ),
            "verification_url": _format_auth_url(login),
            "expires_in": login.expires_in,
        }, 202


def check_auth_status(session_file: Path) -> tuple[dict, int]:
    """Implementation logic for checking authentication status."""
    if not session_file.exists():
        return {
            "authenticated": False,
            "message": "No session file found",
        }, 200

    session = BrowserSession()
    session.load_session_from_file(session_file)

    if session.check_login():
        user_info = {
            "id": session.user.id,
            "username": session.user.username if hasattr(session.user, "username") else "N/A",
            "email": session.user.email if hasattr(session.user, "email") else "N/A",
        }
        return {
            "authenticated": True,
            "message": "Valid TIDAL session",
            "user": user_info,
        }, 200

    return {
        "authenticated": False,
        "message": "Invalid or expired session",
    }, 200

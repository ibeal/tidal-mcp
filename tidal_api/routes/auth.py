"""Authentication route implementation logic."""
from pathlib import Path
from tidal_api.browser_session import BrowserSession


def handle_login(session_file: Path, log_fn=None) -> dict:
    """Implementation logic for TIDAL login."""
    session = BrowserSession()

    def default_log(msg):
        print(f"TIDAL AUTH: {msg}")

    log_message = log_fn or default_log

    try:
        login_success = session.login_session_file_auto(session_file, fn_print=log_message)

        if login_success:
            return {
                "status": "success",
                "message": "Successfully authenticated with TIDAL",
                "user_id": session.user.id
            }, 200
        else:
            return {
                "status": "error",
                "message": "Authentication failed"
            }, 401

    except TimeoutError:
        return {
            "status": "error",
            "message": "Authentication timed out"
        }, 408

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }, 500


def check_auth_status(session_file: Path) -> dict:
    """Implementation logic for checking authentication status."""
    if not session_file.exists():
        return {
            "authenticated": False,
            "message": "No session file found"
        }, 200

    session = BrowserSession()
    login_success = session.login_session_file_auto(session_file)

    if login_success:
        user_info = {
            "id": session.user.id,
            "username": session.user.username if hasattr(session.user, 'username') else "N/A",
            "email": session.user.email if hasattr(session.user, 'email') else "N/A"
        }

        return {
            "authenticated": True,
            "message": "Valid TIDAL session",
            "user": user_info
        }, 200
    else:
        return {
            "authenticated": False,
            "message": "Invalid or expired session"
        }, 200

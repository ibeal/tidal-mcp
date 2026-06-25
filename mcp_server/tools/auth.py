"""Authentication implementation logic."""
import requests
from typing import Any, Dict


def tidal_login(flask_app_url: str) -> Dict[str, Any]:
    """Trigger or poll the non-blocking TIDAL OAuth login flow.

    The Flask endpoint returns one of:
      - status="success" once the session is valid.
      - status="pending" with a verification_url the user must open.
      - status="error" on failure.
    """
    try:
        response = requests.get(f"{flask_app_url}/api/auth/login", timeout=10)
    except requests.RequestException as e:
        return {
            "status": "error",
            "message": f"Failed to connect to TIDAL authentication service: {e}",
        }

    try:
        return response.json()
    except ValueError:
        return {
            "status": "error",
            "message": f"Unexpected response from auth service (HTTP {response.status_code})",
        }

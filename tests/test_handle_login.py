"""
Smoke tests for tidal_api.routes.auth.handle_login — the non-blocking,
stateful OAuth handler.

Covers each branch:
- Cached valid session file → success.
- No pending login → starts one, returns 202 + verification_url.
- Pending login, future not done → re-returns the same pending URL.
- Pending login, future done + check_login() ok → saves session, success.
- Pending login, future done + check_login() failed → error.
- Pending login, future raised → error.
- check_auth_status: missing file, valid session, invalid session.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import tidal_api.routes.auth as auth_module
from tidal_api.routes.auth import handle_login, check_auth_status


def _reset_pending():
    auth_module._PENDING_LOGIN = None


def _fake_login(uri="link.tidal.com/ABCDE", expires_in=300):
    return MagicMock(verification_uri_complete=uri, expires_in=expires_in)


def _fake_future(done=False, exc=None):
    fut = MagicMock()
    fut.done.return_value = done
    if exc is not None:
        fut.result.side_effect = exc
    else:
        fut.result.return_value = None
    return fut


def _patch_session(check_login_returns, save_calls=None, user_id=42):
    """Build a BrowserSession mock instance."""
    session = MagicMock()
    session.check_login.side_effect = check_login_returns if isinstance(check_login_returns, list) else [check_login_returns]
    session.user.id = user_id
    if save_calls is not None:
        session.save_session_to_file.side_effect = save_calls
    return session


class TestCachedSession:
    def test_returns_success_when_session_file_valid(self, tmp_path):
        _reset_pending()
        session_file = tmp_path / "session.json"
        session_file.write_text("{}")

        fake_session = _patch_session(check_login_returns=True, user_id=99)
        with patch.object(auth_module, "BrowserSession", return_value=fake_session):
            result, status = handle_login(session_file)

        assert status == 200
        assert result == {
            "status": "success",
            "message": "Already authenticated with TIDAL",
            "user_id": 99,
        }
        assert auth_module._PENDING_LOGIN is None
        fake_session.load_session_from_file.assert_called_once_with(session_file)

    def test_falls_through_when_session_file_invalid(self, tmp_path):
        _reset_pending()
        session_file = tmp_path / "session.json"
        session_file.write_text("{}")

        # First session (cache check) reports invalid; a *new* BrowserSession is then
        # constructed for the OAuth login attempt.
        invalid_session = _patch_session(check_login_returns=False)
        new_session = MagicMock()
        new_session.login_oauth.return_value = (_fake_login(), _fake_future(done=False))

        with patch.object(
            auth_module, "BrowserSession", side_effect=[invalid_session, new_session]
        ):
            result, status = handle_login(session_file)

        assert status == 202
        assert result["status"] == "pending"
        assert result["verification_url"].startswith("https://")
        assert auth_module._PENDING_LOGIN is not None
        _reset_pending()


class TestNewLogin:
    def test_starts_oauth_and_returns_url(self, tmp_path):
        _reset_pending()
        session_file = tmp_path / "missing.json"

        new_session = MagicMock()
        new_session.login_oauth.return_value = (
            _fake_login(uri="link.tidal.com/ZZZZZ", expires_in=600),
            _fake_future(done=False),
        )

        with patch.object(auth_module, "BrowserSession", return_value=new_session):
            result, status = handle_login(session_file)

        assert status == 202
        assert result["status"] == "pending"
        assert result["verification_url"] == "https://link.tidal.com/ZZZZZ"
        assert result["expires_in"] == 600
        assert auth_module._PENDING_LOGIN is not None
        _reset_pending()

    def test_preserves_http_scheme_when_already_present(self, tmp_path):
        _reset_pending()
        session_file = tmp_path / "missing.json"

        new_session = MagicMock()
        new_session.login_oauth.return_value = (
            _fake_login(uri="https://link.tidal.com/PREFIXED"),
            _fake_future(done=False),
        )

        with patch.object(auth_module, "BrowserSession", return_value=new_session):
            result, _ = handle_login(session_file)

        assert result["verification_url"] == "https://link.tidal.com/PREFIXED"
        _reset_pending()


class TestPendingLogin:
    def test_pending_not_done_returns_same_url(self, tmp_path):
        _reset_pending()
        session_file = tmp_path / "missing.json"

        session = MagicMock()
        login = _fake_login(uri="link.tidal.com/STILLWAITING")
        future = _fake_future(done=False)
        auth_module._PENDING_LOGIN = {
            "session": session,
            "login": login,
            "future": future,
        }

        result, status = handle_login(session_file)

        assert status == 202
        assert result["status"] == "pending"
        assert result["verification_url"] == "https://link.tidal.com/STILLWAITING"
        assert auth_module._PENDING_LOGIN is not None
        _reset_pending()

    def test_pending_done_and_valid_returns_success(self, tmp_path):
        _reset_pending()
        session_file = tmp_path / "missing.json"

        session = MagicMock()
        session.check_login.return_value = True
        session.user.id = 1234

        login = _fake_login()
        future = _fake_future(done=True)
        auth_module._PENDING_LOGIN = {
            "session": session,
            "login": login,
            "future": future,
        }

        result, status = handle_login(session_file)

        assert status == 200
        assert result == {
            "status": "success",
            "message": "Successfully authenticated with TIDAL",
            "user_id": 1234,
        }
        session.save_session_to_file.assert_called_once_with(session_file)
        assert auth_module._PENDING_LOGIN is None

    def test_pending_done_but_invalid_returns_error(self, tmp_path):
        _reset_pending()
        session_file = tmp_path / "missing.json"

        session = MagicMock()
        session.check_login.return_value = False

        auth_module._PENDING_LOGIN = {
            "session": session,
            "login": _fake_login(),
            "future": _fake_future(done=True),
        }

        result, status = handle_login(session_file)

        assert status == 401
        assert result["status"] == "error"
        session.save_session_to_file.assert_not_called()
        assert auth_module._PENDING_LOGIN is None

    def test_pending_future_raised_returns_error(self, tmp_path):
        _reset_pending()
        session_file = tmp_path / "missing.json"

        auth_module._PENDING_LOGIN = {
            "session": MagicMock(),
            "login": _fake_login(),
            "future": _fake_future(done=True, exc=RuntimeError("boom")),
        }

        result, status = handle_login(session_file)

        assert status == 500
        assert result["status"] == "error"
        assert "boom" in result["message"]
        assert auth_module._PENDING_LOGIN is None

    def test_pending_future_timeout_returns_408(self, tmp_path):
        _reset_pending()
        session_file = tmp_path / "missing.json"

        auth_module._PENDING_LOGIN = {
            "session": MagicMock(),
            "login": _fake_login(),
            "future": _fake_future(done=True, exc=TimeoutError()),
        }

        result, status = handle_login(session_file)

        assert status == 408
        assert result["status"] == "error"
        assert auth_module._PENDING_LOGIN is None


class TestCheckAuthStatus:
    def test_missing_file(self, tmp_path):
        result, status = check_auth_status(tmp_path / "nope.json")
        assert status == 200
        assert result == {
            "authenticated": False,
            "message": "No session file found",
        }

    def test_valid_session(self, tmp_path):
        session_file = tmp_path / "session.json"
        session_file.write_text("{}")

        fake_session = MagicMock()
        fake_session.check_login.return_value = True
        fake_session.user.id = 7
        fake_session.user.username = "musiclover"
        fake_session.user.email = "x@example.com"

        with patch.object(auth_module, "BrowserSession", return_value=fake_session):
            result, status = check_auth_status(session_file)

        assert status == 200
        assert result["authenticated"] is True
        assert result["user"] == {"id": 7, "username": "musiclover", "email": "x@example.com"}

    def test_invalid_session_does_not_trigger_login(self, tmp_path):
        """Regression: stale session must not kick off a browser OAuth flow."""
        session_file = tmp_path / "session.json"
        session_file.write_text("{}")

        fake_session = MagicMock()
        fake_session.check_login.return_value = False

        with patch.object(auth_module, "BrowserSession", return_value=fake_session):
            result, status = check_auth_status(session_file)

        assert status == 200
        assert result == {
            "authenticated": False,
            "message": "Invalid or expired session",
        }
        fake_session.login_oauth.assert_not_called()
        fake_session.login_pkce.assert_not_called()

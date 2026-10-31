"""
VisionGuard AI - Google OAuth 2.0 & Account Linking Test Suite.

Validates:
1. Google OAuth initiation, redirect, and state generation.
2. Graceful error handling for missing configuration, user cancellation, and unverified emails.
3. First-time Google citizen registration with strict role enforcement (citizen only).
4. Returning linked Google user authentication.
5. Anti-Account-Takeover (ATO) protection: prevents silent account merges when email matches.
6. PII protection: avoids leaking pending email/username into URL query strings.
7. Explicit password-gated confirmation flow (/api/auth/google/confirm-link).
8. Brute-force rate limiting on password attempts during account linking.
9. Duplicate Google identity collision prevention.
10. Google unlinking safeguards (prevents locking out pure Google accounts).
11. Defense-in-depth token claims validation (issuer, expiration, audience).
12. CSRF protection on account linking.
"""

import os
import time
import pytest
from unittest.mock import patch, MagicMock

from app.server import create_app
from database.db import init_db, get_db_connection
from database.auth import (
    create_user,
    get_user_by_id,
    get_user_by_email,
    get_user_by_google_sub,
    ROLE_CITIZEN,
    ROLE_INSPECTOR,
    ROLE_ADMIN,
)


MOCK_GOOGLE_METADATA = {
    "issuer": "https://accounts.google.com",
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": "https://oauth2.googleapis.com/token",
    "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
}


@pytest.fixture
def oauth_app(tmp_path):
    """Creates a test Flask application configured for Google OAuth testing."""
    test_db = str(tmp_path / "test_oauth.db")
    init_db(test_db)

    app = create_app(
        test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db,
            "AUTH_ENABLED": True,
            "ENFORCE_CSRF": False,
            "SECRET_KEY": "test_secret_key_google_oauth_visionguard_32bytes",
            "GOOGLE_CLIENT_ID": "mock-google-client-id-12345.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "mock-google-client-secret-xyz",
            "GOOGLE_SERVER_METADATA": MOCK_GOOGLE_METADATA,
        }
    )
    return app


@pytest.fixture
def oauth_client(oauth_app):
    return oauth_app.test_client()


# =============================================================================
# 1. Configuration & Initiation Tests
# =============================================================================

def test_google_oauth_status_when_configured(oauth_client):
    """Verifies /api/auth/status reports google_oauth_configured is True."""
    res = oauth_client.get("/api/auth/status")
    assert res.status_code == 200
    data = res.get_json()
    assert data["google_oauth_configured"] is True


def test_google_oauth_status_when_unconfigured(tmp_path):
    """Verifies /api/auth/status reports False when credentials are not configured."""
    test_db = str(tmp_path / "test_no_oauth.db")
    init_db(test_db)

    app = create_app(
        test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db,
            "AUTH_ENABLED": True,
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
        }
    )
    client = app.test_client()
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.get_json()["google_oauth_configured"] is False

    # Attempting to start OAuth flow without credentials redirects with error
    res_auth = client.get("/auth/google")
    assert res_auth.status_code == 302
    assert "error=oauth_not_configured" in res_auth.headers["Location"]


def test_google_oauth_initiation_redirect(oauth_client):
    """Verifies /auth/google initiates the authorization redirect with proper scopes."""
    res = oauth_client.get("/auth/google")
    assert res.status_code == 302
    location = res.headers["Location"]
    assert "accounts.google.com" in location
    assert "client_id=mock-google-client-id" in location
    assert "scope=" in location
    assert "state=" in location


def test_google_oauth_initiation_preserves_return_url(oauth_client):
    """Verifies return URL is preserved across OAuth redirect in session."""
    with oauth_client.session_transaction() as sess:
        pass  # Initialize session cookie

    res = oauth_client.get("/auth/google?return=/records")
    assert res.status_code == 302

    with oauth_client.session_transaction() as sess:
        assert sess.get("oauth_return_url") == "/records"


# =============================================================================
# 2. Callback Error Handling & Claims Validation Tests
# =============================================================================

def test_google_oauth_callback_user_cancelled(oauth_client):
    """Verifies that user cancelling Google consent redirects cleanly to /login?error=google_cancelled."""
    res = oauth_client.get("/auth/google/callback?error=access_denied")
    assert res.status_code == 302
    assert "/login?error=google_cancelled" in res.headers["Location"]


def test_google_oauth_callback_unverified_email_rejected(oauth_client):
    """Verifies that an unverified Google email is strictly rejected."""
    mock_token = {
        "access_token": "mock_token_abc",
        "token_type": "Bearer",
        "userinfo": {
            "sub": "google_sub_unverified_1",
            "email": "unverified@example.com",
            "email_verified": False,
            "name": "Unverified User",
        },
    }

    with patch("app.server.oauth.google.authorize_access_token", return_value=mock_token):
        res = oauth_client.get("/auth/google/callback")
        assert res.status_code == 302
        assert "/login?error=email_not_verified" in res.headers["Location"]


def test_google_oauth_callback_untrusted_issuer_rejected(oauth_client):
    """Verifies that an ID token with an untrusted issuer is rejected."""
    mock_token = {
        "access_token": "mock_token_bad_iss",
        "token_type": "Bearer",
        "userinfo": {
            "sub": "sub_spoofed",
            "email": "spoof@example.com",
            "email_verified": True,
            "iss": "https://untrusted-identity-provider.com",
        },
    }

    with patch("app.server.oauth.google.authorize_access_token", return_value=mock_token):
        res = oauth_client.get("/auth/google/callback")
        assert res.status_code == 302
        assert "/login?error=invalid_issuer" in res.headers["Location"]


def test_google_oauth_callback_expired_token_rejected(oauth_client):
    """Verifies that an expired ID token is rejected."""
    mock_token = {
        "access_token": "mock_token_exp",
        "token_type": "Bearer",
        "userinfo": {
            "sub": "sub_exp",
            "email": "exp_token@example.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "exp": time.time() - 3600,  # 1 hour in the past
        },
    }

    with patch("app.server.oauth.google.authorize_access_token", return_value=mock_token):
        res = oauth_client.get("/auth/google/callback")
        assert res.status_code == 302
        assert "/login?error=token_expired" in res.headers["Location"]


# =============================================================================
# 3. First-Time Registration Tests (Citizen Role Enforcement)
# =============================================================================

def test_google_oauth_first_time_registration_creates_citizen(oauth_app, oauth_client):
    """
    Verifies that a new Google user is provisioned as a citizen account ONLY,
    with an unguessable disabled password hash and active authenticated session.
    """
    mock_token = {
        "access_token": "mock_access_token_123",
        "token_type": "Bearer",
        "userinfo": {
            "sub": "google_sub_new_citizen_999",
            "email": "jane.citizen@gmail.com",
            "email_verified": True,
            "name": "Jane Citizen",
            "picture": "https://lh3.googleusercontent.com/a/mock_avatar",
        },
    }

    with patch("app.server.oauth.google.authorize_access_token", return_value=mock_token):
        res = oauth_client.get("/auth/google/callback")
        assert res.status_code == 302
        assert "/create_home?welcome=google" in res.headers["Location"]

    # Verify session authentication
    with oauth_client.session_transaction() as sess:
        assert sess.get("user_id") is not None
        assert sess.get("role") == ROLE_CITIZEN

    # Verify database record
    db_path = oauth_app.config["DATABASE_PATH"]
    user = get_user_by_google_sub("google_sub_new_citizen_999", db_path=db_path)
    assert user is not None
    assert user["role"] == ROLE_CITIZEN
    assert user["email"] == "jane.citizen@gmail.com"
    assert user["auth_provider"] == "google"
    assert user["avatar_url"] == "https://lh3.googleusercontent.com/a/mock_avatar"

    # Verify password hash is disabled
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE id = ?;", (user["id"],))
    pw_hash = cur.fetchone()["password_hash"]
    conn.close()
    assert pw_hash.startswith("!google_oauth_disabled_")


# =============================================================================
# 4. Returning Google User Authentication Tests
# =============================================================================

def test_google_oauth_existing_linked_user_login(oauth_app, oauth_client):
    """Verifies that an existing user with matching google_sub logs in directly."""
    db_path = oauth_app.config["DATABASE_PATH"]

    # Create an inspector who has previously linked Google
    user = create_user("field_inspector_bob", "SecurePass123!", role=ROLE_INSPECTOR, email="bob@city.gov", db_path=db_path)
    from database.auth import link_google_to_user
    link_google_to_user(user["id"], google_sub="google_sub_bob_888", db_path=db_path)

    mock_token = {
        "access_token": "mock_token_bob",
        "token_type": "Bearer",
        "userinfo": {
            "sub": "google_sub_bob_888",
            "email": "bob@city.gov",
            "email_verified": True,
            "name": "Bob Inspector",
        },
    }

    with patch("app.server.oauth.google.authorize_access_token", return_value=mock_token):
        res = oauth_client.get("/auth/google/callback")
        assert res.status_code == 302
        # Municipal inspector redirects to /app
        assert res.headers["Location"].endswith("/app")

    # Verify session contains inspector role
    with oauth_client.session_transaction() as sess:
        assert sess.get("user_id") == user["id"]
        assert sess.get("username") == "field_inspector_bob"
        assert sess.get("role") == ROLE_INSPECTOR


# =============================================================================
# 5. Anti-Account-Takeover (ATO) & PII Protection Tests
# =============================================================================

def test_google_oauth_matching_email_triggers_linking_flow_with_pii_protection(oauth_app, oauth_client):
    """
    ANTI-ATO & PRIVACY TEST:
    If a Google identity email matches an existing password-based account,
    do NOT silently log in or merge. Redirect to explicit account linking flow.
    PII protection: Ensure email and username are NOT exposed in the URL query string.
    """
    db_path = oauth_app.config["DATABASE_PATH"]
    existing_user = create_user("alice_original", "StrongPassword123!", role=ROLE_CITIZEN, email="alice@example.com", db_path=db_path)

    mock_token = {
        "access_token": "mock_token_alice",
        "token_type": "Bearer",
        "userinfo": {
            "sub": "google_sub_alice_777",
            "email": "alice@example.com",
            "email_verified": True,
            "name": "Alice Smith",
        },
    }

    with patch("app.server.oauth.google.authorize_access_token", return_value=mock_token):
        res = oauth_client.get("/auth/google/callback")
        assert res.status_code == 302
        location = res.headers["Location"]
        assert location.endswith("/login?link_pending=1")
        # Ensure no PII leaked into URL
        assert "alice@example.com" not in location
        assert "alice%40example.com" not in location
        assert "alice_original" not in location

    # Verify user is NOT authenticated yet
    with oauth_client.session_transaction() as sess:
        assert "user_id" not in sess
        pending = sess.get("pending_google_link")
        assert pending is not None
        assert pending["user_id"] == existing_user["id"]
        assert pending["google_sub"] == "google_sub_alice_777"
        assert pending["email"] == "alice@example.com"

    # Verify /api/auth/status securely supplies pending_link data over authenticated JSON
    res_status = oauth_client.get("/api/auth/status")
    assert res_status.status_code == 200
    st_data = res_status.get_json()
    assert st_data["link_pending"] is True
    assert st_data["pending_link"]["email"] == "alice@example.com"
    assert st_data["pending_link"]["username"] == "alice_original"


def test_confirm_link_fails_with_invalid_password(oauth_app, oauth_client):
    """Verifies that confirming account linking with the wrong password is rejected."""
    db_path = oauth_app.config["DATABASE_PATH"]
    user = create_user("charlie_test", "RealPassword123!", role=ROLE_CITIZEN, email="charlie@example.com", db_path=db_path)

    with oauth_client.session_transaction() as sess:
        sess["pending_google_link"] = {
            "user_id": user["id"],
            "username": "charlie_test",
            "email": "charlie@example.com",
            "google_sub": "google_sub_charlie_555",
            "timestamp": time.time(),
        }

    res = oauth_client.post(
        "/api/auth/google/confirm-link",
        json={"password": "WrongPassword999!"}
    )
    assert res.status_code == 401
    data = res.get_json()
    assert data["status"] == "error"
    assert data["error_code"] == "INVALID_PASSWORD"

    # Verify google_sub was NOT linked
    reloaded = get_user_by_id(user["id"], db_path=db_path)
    assert reloaded.get("google_sub") is None


def test_confirm_link_succeeds_with_valid_password(oauth_app, oauth_client):
    """Verifies that providing the correct password successfully links Google and authenticates."""
    db_path = oauth_app.config["DATABASE_PATH"]
    user = create_user("diana_test", "CorrectPassword123!", role=ROLE_CITIZEN, email="diana@example.com", db_path=db_path)

    with oauth_client.session_transaction() as sess:
        sess["pending_google_link"] = {
            "user_id": user["id"],
            "username": "diana_test",
            "email": "diana@example.com",
            "google_sub": "google_sub_diana_444",
            "avatar_url": "https://avatar.example.com/diana.png",
            "timestamp": time.time(),
        }

    res = oauth_client.post(
        "/api/auth/google/confirm-link",
        json={"password": "CorrectPassword123!"}
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["user"]["auth_provider"] == "both"

    # Verify session is now authenticated
    with oauth_client.session_transaction() as sess:
        assert sess.get("user_id") == user["id"]
        assert sess.get("username") == "diana_test"
        assert sess.get("pending_google_link") is None

    # Verify DB record updated
    reloaded = get_user_by_id(user["id"], db_path=db_path)
    assert reloaded["google_sub"] == "google_sub_diana_444"
    assert reloaded["auth_provider"] == "both"


def test_confirm_link_rate_limiting(oauth_app, oauth_client):
    """Verifies that 5 failed password attempts terminates the linking session for security."""
    db_path = oauth_app.config["DATABASE_PATH"]
    user = create_user("rate_limit_user", "CorrectPassword123!", role=ROLE_CITIZEN, email="rl@example.com", db_path=db_path)

    with oauth_client.session_transaction() as sess:
        sess["pending_google_link"] = {
            "user_id": user["id"],
            "username": "rate_limit_user",
            "email": "rl@example.com",
            "google_sub": "sub_rl",
            "timestamp": time.time(),
            "failed_attempts": 4,  # Next failure will reach 5
        }

    # Attempt 5: fails
    res1 = oauth_client.post("/api/auth/google/confirm-link", json={"password": "BadPassword!"})
    assert res1.status_code == 401

    # Attempt 6: triggers 429 TOO_MANY_ATTEMPTS and purges session
    res2 = oauth_client.post("/api/auth/google/confirm-link", json={"password": "BadPassword!"})
    assert res2.status_code == 429
    assert res2.get_json()["error_code"] == "TOO_MANY_ATTEMPTS"

    with oauth_client.session_transaction() as sess:
        assert "pending_google_link" not in sess


def test_confirm_link_fails_when_expired(oauth_app, oauth_client):
    """Verifies that an account link request older than 15 minutes expires."""
    db_path = oauth_app.config["DATABASE_PATH"]
    user = create_user("expired_user", "Pass12345!", role=ROLE_CITIZEN, email="exp@example.com", db_path=db_path)

    with oauth_client.session_transaction() as sess:
        sess["pending_google_link"] = {
            "user_id": user["id"],
            "username": "expired_user",
            "email": "exp@example.com",
            "google_sub": "google_sub_exp",
            "timestamp": time.time() - 1000,  # 1000s > 900s
        }

    res = oauth_client.post(
        "/api/auth/google/confirm-link",
        json={"password": "Pass12345!"}
    )
    assert res.status_code == 400
    assert res.get_json()["error_code"] == "LINK_EXPIRED"


def test_confirm_link_csrf_enforcement(tmp_path):
    """Verifies that CSRF protection is verified on account linking when CSRF enforcement is enabled."""
    test_db = str(tmp_path / "test_csrf_link.db")
    init_db(test_db)

    app = create_app(
        test_config={
            "TESTING": True,
            "DATABASE_PATH": test_db,
            "AUTH_ENABLED": True,
            "ENFORCE_CSRF": True,
            "SECRET_KEY": "test_secret_key_google_oauth_visionguard_32bytes",
            "GOOGLE_CLIENT_ID": "mock-client-id",
            "GOOGLE_CLIENT_SECRET": "mock-secret",
            "GOOGLE_SERVER_METADATA": MOCK_GOOGLE_METADATA,
        }
    )
    client = app.test_client()
    user = create_user("csrf_user", "MyPass123!", role=ROLE_CITIZEN, email="csrf@example.com", db_path=test_db)

    with client.session_transaction() as sess:
        sess["csrf_token"] = "valid_csrf_token_123"
        sess["pending_google_link"] = {
            "user_id": user["id"],
            "username": "csrf_user",
            "email": "csrf@example.com",
            "google_sub": "sub_csrf",
            "timestamp": time.time(),
        }

    # Post with invalid CSRF token
    res_bad = client.post(
        "/api/auth/google/confirm-link",
        headers={"X-CSRF-Token": "bad_token"},
        json={"password": "MyPass123!"}
    )
    assert res_bad.status_code == 403
    assert res_bad.get_json()["error_code"] == "CSRF_TOKEN_INVALID"

    # Post with valid CSRF token
    res_good = client.post(
        "/api/auth/google/confirm-link",
        headers={"X-CSRF-Token": "valid_csrf_token_123"},
        json={"password": "MyPass123!"}
    )
    assert res_good.status_code == 200
    assert res_good.get_json()["status"] == "success"


def test_cancel_link_clears_pending_state(oauth_client):
    """Verifies /api/auth/google/cancel-link safely clears session state."""
    with oauth_client.session_transaction() as sess:
        sess["pending_google_link"] = {"user_id": 1, "google_sub": "sub_xyz", "timestamp": time.time()}

    res = oauth_client.post("/api/auth/google/cancel-link")
    assert res.status_code == 200
    assert res.get_json()["status"] == "success"

    with oauth_client.session_transaction() as sess:
        assert "pending_google_link" not in sess


# =============================================================================
# 6. Unlinking Safeguards & Duplicate Prevention
# =============================================================================

def test_unlink_google_allowed_for_dual_auth_user(oauth_app, oauth_client):
    """Verifies that a user with both password and Google can safely unlink Google."""
    db_path = oauth_app.config["DATABASE_PATH"]
    user = create_user("dual_user", "MyPassword123!", role=ROLE_CITIZEN, email="dual@example.com", db_path=db_path)
    from database.auth import link_google_to_user
    link_google_to_user(user["id"], "google_sub_dual_111", db_path=db_path)

    # Log in as dual_user
    with oauth_client.session_transaction() as sess:
        sess["user_id"] = user["id"]
        sess["username"] = "dual_user"
        sess["role"] = ROLE_CITIZEN

    res = oauth_client.post("/api/auth/google/unlink")
    assert res.status_code == 200
    assert res.get_json()["status"] == "success"

    reloaded = get_user_by_id(user["id"], db_path=db_path)
    assert reloaded["google_sub"] is None
    assert reloaded["auth_provider"] == "local"


def test_unlink_google_forbidden_for_pure_google_user(oauth_app, oauth_client):
    """Verifies that unlinking Google is rejected for accounts without a local password."""
    db_path = oauth_app.config["DATABASE_PATH"]
    from database.auth import create_google_user
    pure_google = create_google_user("pure_google_user", "pure@example.com", "google_sub_pure_222", db_path=db_path)

    with oauth_client.session_transaction() as sess:
        sess["user_id"] = pure_google["id"]
        sess["username"] = "pure_google_user"
        sess["role"] = ROLE_CITIZEN

    res = oauth_client.post("/api/auth/google/unlink")
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert data["error_code"] == "UNLINK_FAILED"
    assert "local password" in data["message"].lower()


def test_duplicate_google_sub_linking_prevented(oauth_app):
    """Verifies that an already linked Google sub cannot be attached to a second user."""
    db_path = oauth_app.config["DATABASE_PATH"]
    user1 = create_user("user_one", "PasswordOne123!", role=ROLE_CITIZEN, email="u1@example.com", db_path=db_path)
    user2 = create_user("user_two", "PasswordTwo123!", role=ROLE_CITIZEN, email="u2@example.com", db_path=db_path)

    from database.auth import link_google_to_user
    link_google_to_user(user1["id"], "shared_google_sub_333", db_path=db_path)

    # Attempt to link same sub to user2
    with pytest.raises(ValueError, match="already linked to another user"):
        link_google_to_user(user2["id"], "shared_google_sub_333", db_path=db_path)

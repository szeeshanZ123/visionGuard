"""
VisionGuard AI - Google OAuth 2.0 & OpenID Connect Service.

Provides secure citizen authentication via Google Identity using Authlib.
Integrates with existing session lifecycle, anti-account-takeover protections,
and role-based access controls.
"""

import os
import logging
from typing import Optional, Dict, Any
from authlib.integrations.flask_client import OAuth
from flask import Flask, current_app

logger = logging.getLogger(__name__)

# Singleton OAuth registry
oauth = OAuth()

# Standard Google OpenID Connect endpoints & trusted issuer
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUER = "https://accounts.google.com"


def is_google_oauth_configured(app: Optional[Flask] = None) -> bool:
    """
    Checks whether Google OAuth client ID and client secret are configured
    in environment variables or Flask application config.
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not client_id and app:
        client_id = app.config.get("GOOGLE_CLIENT_ID")
    if not client_secret and app:
        client_secret = app.config.get("GOOGLE_CLIENT_SECRET")

    return bool(client_id and client_secret and str(client_id).strip() and str(client_secret).strip())


def init_oauth(app: Flask) -> OAuth:
    """
    Initializes the Authlib OAuth extension with the Flask app
    and registers the Google OpenID Connect provider with standard endpoints.
    """
    oauth.init_app(app)
    if hasattr(oauth, "_clients"):
        oauth._clients.clear()

    client_id = (os.environ.get("GOOGLE_CLIENT_ID") or app.config.get("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_CLIENT_SECRET") or app.config.get("GOOGLE_CLIENT_SECRET") or "").strip()

    # Pre-configure explicit Google OpenID Connect endpoints and issuer
    # so authorize_redirect executes cleanly and instantaneously without blocking on dynamic discovery.
    register_kwargs: Dict[str, Any] = {
        "name": "google",
        "client_id": client_id,
        "client_secret": client_secret,
        "authorize_url": GOOGLE_AUTH_URL,
        "access_token_url": GOOGLE_TOKEN_URL,
        "userinfo_endpoint": GOOGLE_USERINFO_URL,
        "jwks_uri": GOOGLE_JWKS_URL,
        "issuer": GOOGLE_ISSUER,
        "client_kwargs": {
            "scope": "openid email profile",
            "prompt": "select_account",
        },
    }

    # Allow custom discovery URL if explicitly requested via environment or config
    custom_conf_url = os.environ.get("GOOGLE_OIDC_CONF_URL") or app.config.get("GOOGLE_OIDC_CONF_URL")
    if custom_conf_url:
        register_kwargs["server_metadata_url"] = custom_conf_url

    oauth.register(**register_kwargs)
    logger.info("Initialized Google OAuth 2.0 service with Authlib.")
    return oauth

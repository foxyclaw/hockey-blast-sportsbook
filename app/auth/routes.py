"""
Auth0 OAuth2/OIDC routes.

Routes:
    GET  /auth/login      → redirect to Auth0 login page
    GET  /auth/callback   → handle Auth0 redirect, issue session
    GET  /auth/logout     → clear session, redirect to Auth0 logout
    GET  /auth/me         → return current user info (requires auth)
"""

import os
from urllib.parse import urlencode

from authlib.integrations.flask_client import OAuth
from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    request,
    session,
    url_for,
    g,
)

from app.auth.jwt_validator import require_auth

auth_bp = Blueprint("auth", __name__)

# OAuth client is initialized in create_app() and attached here
oauth = OAuth()


def init_oauth(app):
    """Register Auth0 as an OAuth client. Called from app factory."""
    oauth.init_app(app)
    oauth.register(
        name="auth0",
        client_id=app.config["AUTH0_CLIENT_ID"],
        client_secret=app.config["AUTH0_CLIENT_SECRET"],
        server_metadata_url=f'https://{app.config["AUTH0_DOMAIN"]}/.well-known/openid-configuration',
        client_kwargs={
            "scope": "openid profile email",
        },
    )


@auth_bp.route("/login")
def login():
    """Redirect the user to Auth0 for authentication."""
    callback_url = current_app.config.get(
        "AUTH0_CALLBACK_URL", url_for("auth.callback", _external=True)
    )
    return oauth.auth0.authorize_redirect(redirect_uri=callback_url)


@auth_bp.route("/callback")
def callback():
    """
    Handle the Auth0 redirect.
    Exchange code for tokens, upsert PredUser, store JWT in session.
    """
    token = oauth.auth0.authorize_access_token()

    # Extract user info from the ID token
    userinfo = token.get("userinfo") or {}

    # Upsert the PredUser
    from app.services.user_service import get_or_create_pred_user
    from app.db import PredSession

    pred_session = PredSession()
    pred_user = get_or_create_pred_user(userinfo, pred_session)
    pred_session.commit()

    # Store the access token and user ID in the Flask session (HttpOnly cookie)
    session["access_token"] = token.get("access_token")
    session["user_id"] = pred_user.id

    # Redirect to the frontend — adjust this URL for your SPA
    frontend_url = current_app.config.get("FRONTEND_URL", "/")
    return redirect(frontend_url)


@auth_bp.route("/logout")
def logout():
    """Clear session and redirect to Auth0 logout."""
    session.clear()

    domain = current_app.config["AUTH0_DOMAIN"]
    client_id = current_app.config["AUTH0_CLIENT_ID"]
    return_to = current_app.config.get("FRONTEND_URL", request.host_url)

    logout_url = f"https://{domain}/v2/logout?" + urlencode(
        {"returnTo": return_to, "client_id": client_id}
    )
    return redirect(logout_url)


@auth_bp.route("/me")
@require_auth
def me():
    """Return current authenticated user's info."""
    user = g.pred_user
    if not user:
        return jsonify({"error": "NOT_FOUND", "message": "User not found"}), 404

    return jsonify(
        {
            "id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "hb_human_id": user.hb_human_id,
            "auth0_sub": user.auth0_sub,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": (
                user.last_login_at.isoformat() if user.last_login_at else None
            ),
        }
    )

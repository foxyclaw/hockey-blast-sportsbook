"""
JWT validation against Auth0 JWKS endpoint.

Uses PyJWT + cryptography to validate RS256 tokens issued by Auth0.
JWKS keys are cached in memory to avoid fetching on every request.
"""

import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any

import jwt
import requests
from flask import current_app, g, jsonify, request

# Simple in-memory JWKS cache
_jwks_cache: dict = {}
_jwks_cache_ts: float = 0.0
_JWKS_CACHE_TTL: int = 3600  # re-fetch JWKS every hour


def _get_jwks() -> dict:
    """Fetch JWKS from Auth0 and cache it."""
    global _jwks_cache, _jwks_cache_ts

    now = time.time()
    if _jwks_cache and (now - _jwks_cache_ts) < _JWKS_CACHE_TTL:
        return _jwks_cache

    domain = current_app.config["AUTH0_DOMAIN"]
    url = f"https://{domain}/.well-known/jwks.json"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_cache_ts = now
    return _jwks_cache


def _get_public_key(kid: str) -> str:
    """Return the PEM public key for a given key ID."""
    jwks = _get_jwks()
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            # PyJWT's algorithms module can construct the key from JWK
            from jwt.algorithms import RSAAlgorithm
            return RSAAlgorithm.from_jwk(key_data)
    raise ValueError(f"Public key not found for kid={kid!r}")


def validate_token(token: str) -> dict[str, Any]:
    """
    Validate a JWT Bearer token against Auth0.

    Returns the decoded payload dict on success.
    Raises jwt.PyJWTError (or subclass) on failure.
    """
    # Decode the header without verification to get the key ID
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    if not kid:
        raise jwt.InvalidTokenError("Token header missing 'kid'")

    public_key = _get_public_key(kid)

    domain = current_app.config["AUTH0_DOMAIN"]
    # ID token audience is always the Auth0 client ID
    audience = current_app.config["AUTH0_CLIENT_ID"]

    payload = jwt.decode(
        token,
        public_key,
        algorithms=current_app.config.get("AUTH0_ALGORITHMS", ["RS256"]),
        audience=audience,
        issuer=f"https://{domain}/",
    )
    return payload


def _extract_token(req) -> str | None:
    """Extract Bearer token from Authorization header."""
    auth_header = req.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def require_auth(f):
    """
    Decorator: validates JWT, sets g.user_sub and g.pred_user.

    g.user_sub  → Auth0 sub claim (string)
    g.pred_user → PredUser ORM object (created if first login)

    Returns 401 JSON on invalid/missing token.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token(request)
        if not token:
            return jsonify({"error": "UNAUTHORIZED", "message": "Bearer token required"}), 401

        try:
            payload = validate_token(token)
        except Exception as exc:
            return jsonify({"error": "UNAUTHORIZED", "message": f"Invalid token: {exc}"}), 401

        g.user_sub = payload["sub"]
        g.jwt_payload = payload

        # Lazy import to avoid circular imports
        from app.services.user_service import get_or_create_pred_user
        from app.db import PredSession

        db = PredSession()
        g.pred_user = get_or_create_pred_user(payload, db)

        # Touch last_seen_at on every authenticated request
        if g.pred_user:
            g.pred_user.last_seen_at = datetime.now(timezone.utc)
            db.flush()

        return f(*args, **kwargs)

    return decorated


def optional_auth(f):
    """
    Like require_auth but doesn't fail on missing token.
    Sets g.pred_user = None if unauthenticated.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token(request)
        g.pred_user = None
        g.user_sub = None

        if token:
            try:
                payload = validate_token(token)
                g.user_sub = payload["sub"]
                g.jwt_payload = payload
                from app.services.user_service import get_or_create_pred_user
                from app.db import PredSession
                db = PredSession()
                g.pred_user = get_or_create_pred_user(payload, db)

                # Touch last_seen_at on every authenticated request
                if g.pred_user:
                    g.pred_user.last_seen_at = datetime.now(timezone.utc)
                    db.flush()
            except Exception:
                pass  # Silently ignore bad tokens in optional auth

        return f(*args, **kwargs)

    return decorated

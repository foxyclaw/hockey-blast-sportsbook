"""
admin_required — decorator that enforces admin access on API routes.

Usage:
    @admin_bp.route("/some-route")
    @require_admin
    def some_route():
        ...
"""

from functools import wraps
from flask import g, jsonify
from app.auth.jwt_validator import require_auth


def require_admin(f):
    """Decorator: require_auth + is_admin check. Returns 403 if not admin."""
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if not getattr(g.pred_user, "is_admin", False):
            return jsonify({"error": "FORBIDDEN", "message": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated

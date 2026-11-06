"""
Standardized JSON response helpers.
"""

from flask import jsonify


def error_response(code: str, message: str, http_status: int = 400):
    """
    Return a standardized error JSON response.

    Example:
        return error_response("NOT_FOUND", "League not found", 404)
    """
    return jsonify({"error": code, "message": message}), http_status


def success_response(data: dict, http_status: int = 200):
    """Wrap data in a success envelope."""
    return jsonify(data), http_status


def reject_if_migrated(league):
    """
    Return a 409 response if ``league`` was migrated to the social site, else None.

    A migrated league (``migrated_at`` set by the hockey-blast.com import) is
    read-only here. Call at the top of every fantasy write handler, right after
    the league is loaded:

        resp = reject_if_migrated(league)
        if resp:
            return resp
    """
    if league is None or getattr(league, "migrated_at", None) is None:
        return None
    return jsonify({
        "error": "league_migrated",
        "message": "This league moved to hockey-blast.com",
        "url": league.migrated_to_url,
    }), 409

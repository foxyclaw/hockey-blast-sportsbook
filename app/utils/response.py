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

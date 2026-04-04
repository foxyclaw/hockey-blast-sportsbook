"""
Flask application factory.

Usage:
    from app import create_app
    app = create_app()

    # Or with explicit config:
    app = create_app("production")
"""

import logging
import os

from flask import Flask, jsonify
from flask_cors import CORS

from app.config import config, get_config
from app.db import init_db


def create_app(config_name: str | None = None) -> Flask:
    """
    Application factory. Creates and configures the Flask app.

    Args:
        config_name: "development" | "testing" | "production" | None
                     Defaults to FLASK_ENV environment variable, then "development".
    """
    app = Flask(__name__)

    # ── Load config ────────────────────────────────────────────────────────────
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    cfg_class = config.get(config_name, config["default"])
    app.config.from_object(cfg_class)

    # ── Logging ────────────────────────────────────────────────────────────────
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO"), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    CORS(
        app,
        origins=app.config.get("CORS_ORIGINS", ["*"]),
        supports_credentials=True,
    )

    # ── Database (dual sessions) ───────────────────────────────────────────────
    init_db(app)

    # ── Auth0 OAuth client ─────────────────────────────────────────────────────
    from app.auth.routes import init_oauth
    init_oauth(app)

    # ── Blueprints ─────────────────────────────────────────────────────────────
    _register_blueprints(app)

    # ── Background scheduler ───────────────────────────────────────────────────
    if not app.config.get("TESTING"):
        # Start scheduler once per process.
        # - Gunicorn: preload_app=True loads this in master; post_fork shuts it down in workers.
        # - Flask dev server: werkzeug reloader fires twice; only start in the child (WERKZEUG_RUN_MAIN=true).
        # - Any other runner (pytest excluded via TESTING): always start.
        _werkzeug_main = os.environ.get("WERKZEUG_RUN_MAIN")
        _should_start = (
            _werkzeug_main is None   # gunicorn or direct python run
            or _werkzeug_main == "true"  # werkzeug reloader child
        )
        if _should_start:
            from app.jobs.grade_results import start_scheduler
            start_scheduler(app)
            from app.services.event_tracker import start_tracker
            start_tracker(app)

    # ── Health check ───────────────────────────────────────────────────────────
    @app.route("/api/health")
    def health():
        """Liveness probe endpoint."""
        return jsonify({"status": "ok", "service": "hockey-blast-predictions"})

    @app.route("/version")
    def version():
        """Show running git commit info."""
        import subprocess
        try:
            commit_hash = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=os.path.dirname(__file__),
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            commit_msg = subprocess.check_output(
                ["git", "log", "-1", "--pretty=%s"],
                cwd=os.path.dirname(__file__),
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            commit_date = subprocess.check_output(
                ["git", "log", "-1", "--format=%cd", "--date=short"],
                cwd=os.path.dirname(__file__),
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            commit_hash = commit_msg = commit_date = "unknown"
        return jsonify({
            "service": "hockey-blast-sportsbook",
            "commit": commit_hash,
            "message": commit_msg,
            "date": commit_date,
        })

    @app.route("/api/health/db")
    def health_db():
        """Readiness probe — checks both DB connections."""
        from app.db import HBSession, PredSession
        results = {}

        try:
            HBSession().execute(__import__("sqlalchemy").text("SELECT 1"))
            results["hb_db"] = "ok"
        except Exception as exc:
            results["hb_db"] = f"error: {exc}"

        try:
            PredSession().execute(__import__("sqlalchemy").text("SELECT 1"))
            results["pred_db"] = "ok"
        except Exception as exc:
            results["pred_db"] = f"error: {exc}"

        all_ok = all(v == "ok" for v in results.values())
        return jsonify({"status": "ok" if all_ok else "degraded", **results}), (
            200 if all_ok else 503
        )

    # ── SPA catch-all — serve index.html for all non-API routes ──────────────
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path):
        """Serve Vue SPA. API routes are matched before this catch-all."""
        from flask import send_from_directory
        import os as _os
        dist = _os.path.join(_os.path.dirname(__file__), "..", "frontend", "dist")
        dist = _os.path.abspath(dist)
        full = _os.path.join(dist, path)
        if path and _os.path.isfile(full):
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")

    # ── Error handlers ─────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        from flask import request as _req
        if _req.path.startswith("/api/") or _req.path.startswith("/auth/"):
            return jsonify({"error": "NOT_FOUND", "message": "Resource not found"}), 404
        dist = _os.path.join(_os.path.dirname(__file__), "..", "frontend", "dist")
        return send_from_directory(_os.path.abspath(dist), "index.html")

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "METHOD_NOT_ALLOWED", "message": str(e)}), 405

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"}), 500

    return app


def _register_blueprints(app: Flask) -> None:
    """Register all blueprints with the app."""
    from app.auth.routes import auth_bp
    from app.blueprints.games import games_bp
    from app.blueprints.picks import picks_bp
    from app.blueprints.leagues import leagues_bp
    from app.blueprints.standings import standings_bp
    from app.blueprints.identity import identity_bp
    from app.blueprints.chat import chat_bp
    from app.blueprints.preferences import preferences_bp
    from app.blueprints.team_connect import team_connect_bp
    from app.blueprints.fantasy import fantasy_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.support import support_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(games_bp, url_prefix="/api/games")
    app.register_blueprint(picks_bp, url_prefix="/api/picks")
    app.register_blueprint(leagues_bp, url_prefix="/api/leagues")
    app.register_blueprint(standings_bp, url_prefix="/api/standings")
    app.register_blueprint(identity_bp, url_prefix="/api/identity")
    app.register_blueprint(chat_bp)
    app.register_blueprint(preferences_bp, url_prefix="/api/preferences")
    app.register_blueprint(team_connect_bp, url_prefix="")
    app.register_blueprint(fantasy_bp, url_prefix="/api/fantasy")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(support_bp, url_prefix="/api/support")

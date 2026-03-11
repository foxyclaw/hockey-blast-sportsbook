"""
Background grader job — grades completed games every GRADER_INTERVAL_MINUTES.

Uses APScheduler (BackgroundScheduler) embedded in the Flask process.
For high-load deployments, swap this for a Celery beat task.

Setup:
    from app.jobs.grade_results import start_scheduler
    start_scheduler(app)

The scheduler is started in the app factory when not testing.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_grade_job():
    """
    Execute the grade_completed_games job.
    Runs inside a Flask application context.
    """
    # We need app context for DB sessions and config
    from flask import current_app

    with current_app.app_context():
        try:
            from app.services.result_grader import grade_completed_games
            summary = grade_completed_games()
            logger.info(
                "[grader] Run complete — graded=%d skipped=%d errors=%d",
                summary.get("graded", 0),
                summary.get("skipped", 0),
                summary.get("errors", 0),
            )
        except Exception as exc:
            logger.exception("[grader] Unhandled exception during grader run: %s", exc)


def start_scheduler(app):
    """
    Start the APScheduler background scheduler.
    Attaches to the Flask app for context.

    Safe to call multiple times — won't double-start.
    Not started in testing mode.
    """
    global _scheduler

    if app.config.get("TESTING"):
        logger.debug("[grader] Testing mode — scheduler not started")
        return

    if _scheduler is not None and _scheduler.running:
        logger.debug("[grader] Scheduler already running")
        return

    interval_minutes = app.config.get("GRADER_INTERVAL_MINUTES", 5)

    _scheduler = BackgroundScheduler(
        job_defaults={
            "coalesce": True,          # Don't run missed jobs multiple times
            "max_instances": 1,        # Only one instance at a time
            "misfire_grace_time": 60,  # 60 sec grace if missed
        }
    )

    # We store the app in the job so we can push an app context
    _app = app

    def _job_with_context():
        with _app.app_context():
            try:
                from app.services.result_grader import grade_completed_games
                summary = grade_completed_games()
                logger.info(
                    "[grader] Run complete — graded=%d skipped=%d errors=%d",
                    summary.get("graded", 0),
                    summary.get("skipped", 0),
                    summary.get("errors", 0),
                )
            except Exception as exc:
                logger.exception("[grader] Error: %s", exc)

    _scheduler.add_job(
        func=_job_with_context,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="grade_results",
        name="Grade completed game picks",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("[grader] Scheduler started. Interval: %d minutes", interval_minutes)

    # Graceful shutdown hook
    import atexit
    atexit.register(stop_scheduler)


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[grader] Scheduler stopped")
        _scheduler = None


def get_scheduler() -> BackgroundScheduler | None:
    """Return the active scheduler instance (or None if not started)."""
    return _scheduler

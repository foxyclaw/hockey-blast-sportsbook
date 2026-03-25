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
from apscheduler.triggers.cron import CronTrigger
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


def run_prediction_snapshot_job():
    """
    Execute the snapshot_upcoming_games job.
    Runs inside a Flask application context.
    """
    from flask import current_app

    with current_app.app_context():
        try:
            from app.services import prediction_snapshot
            summary = prediction_snapshot.snapshot_upcoming_games()
            logger.info(
                "[snapshot] Run complete — snapshotted=%d skipped=%d errors=%d",
                summary.get("snapshotted", 0),
                summary.get("skipped", 0),
                summary.get("errors", 0),
            )
        except Exception as exc:
            logger.exception("[snapshot] Unhandled exception during snapshot run: %s", exc)


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

    def _snapshot_job_with_context():
        with _app.app_context():
            try:
                from app.services import prediction_snapshot
                summary = prediction_snapshot.snapshot_upcoming_games()
                logger.info(
                    "[snapshot] Run complete — snapshotted=%d skipped=%d errors=%d",
                    summary.get("snapshotted", 0),
                    summary.get("skipped", 0),
                    summary.get("errors", 0),
                )
            except Exception as exc:
                logger.exception("[snapshot] Error: %s", exc)

    _scheduler.add_job(
        func=_snapshot_job_with_context,
        trigger=CronTrigger(hour=3, minute=3, timezone="America/Los_Angeles"),
        id="snapshot_predictions",
        name="Snapshot upcoming game predictions",
        replace_existing=True,
    )

    def _draft_advance_job():
        """
        Check all active drafts for expired pick deadlines.
        Runs every minute so auto-pick fires promptly.
        """
        with _app.app_context():
            try:
                from datetime import datetime, timezone as _tz
                from sqlalchemy import select
                from app.db import PredSession
                from app.models.fantasy_league import FantasyLeague
                from app.services.fantasy_draft_service import advance_draft

                pred = PredSession()
                now = datetime.now(_tz.utc)
                drafting_leagues = pred.execute(
                    select(FantasyLeague.id).where(
                        FantasyLeague.status.in_(["drafting", "draft_open"])
                    )
                ).scalars().all()

                for league_id in drafting_leagues:
                    try:
                        advance_draft(league_id)
                    except Exception as e:
                        logger.warning("[draft] advance_draft(%d) error: %s", league_id, e)

                if drafting_leagues:
                    logger.debug("[draft] Checked %d active draft(s)", len(drafting_leagues))
            except Exception as exc:
                logger.exception("[draft] Unhandled error in draft advance job: %s", exc)

    _scheduler.add_job(
        func=_draft_advance_job,
        trigger=IntervalTrigger(minutes=1),
        id="advance_drafts",
        name="Advance fantasy draft picks on deadline",
        replace_existing=True,
    )


    def _fantasy_score_job():
        """Score completed games for all active fantasy leagues."""
        with _app.app_context():
            try:
                from app.services.fantasy_scoring_service import score_active_leagues
                summary = score_active_leagues()
                if summary["games"] > 0 or summary["errors"] > 0:
                    logger.info(
                        "[fantasy] Scored leagues=%d games=%d errors=%d",
                        summary.get("leagues", 0),
                        summary.get("games", 0),
                        summary.get("errors", 0),
                    )
            except Exception as exc:
                logger.exception("[fantasy] Unhandled error in fantasy score job: %s", exc)

    _scheduler.add_job(
        func=_fantasy_score_job,
        trigger=IntervalTrigger(minutes=5),
        id="fantasy_scoring",
        name="Score fantasy games",
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

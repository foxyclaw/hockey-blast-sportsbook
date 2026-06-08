"""
Prediction snapshot service — logs skill-based game predictions.

Runs once daily at 3:03 AM PST.
Look-ahead window = 24 hours (matches run period).
Idempotent: skips games already logged (unique constraint on game_id).
"""

import logging
import zoneinfo
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import HBSession, PredSession
from app.models.game_prediction_log import GamePredictionLog
from app.services.skill_snapshot import get_team_avg_skill

logger = logging.getLogger(__name__)

_PACIFIC = zoneinfo.ZoneInfo("America/Los_Angeles")


def snapshot_upcoming_games() -> dict:
    """
    Find all games starting in the next 24 hours that don't have a
    game_prediction_log row yet, and snapshot the skill-based prediction
    for each one.

    Returns:
        {"snapshotted": N, "skipped": N, "errors": N}
    """
    try:
        from hockey_blast_common_lib.models import Game, Team
        from hockey_blast_common_lib.game_status import StatusId
    except ImportError:
        logger.error("[snapshot] hockey_blast_common_lib not available")
        return {"snapshotted": 0, "skipped": 0, "errors": 1}

    look_ahead_hours = 24
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=look_ahead_hours)

    hb_session = HBSession()
    pred_session = PredSession()

    snapshotted = 0
    skipped = 0
    errors = 0

    # Fetch candidate games: Scheduled, home_team_id not null
    stmt = select(Game).where(
        Game.status_id == StatusId.SCHEDULED,
        Game.home_team_id.isnot(None),
    )
    candidate_games = hb_session.execute(stmt).scalars().all()

    # Filter to games within the look-ahead window by parsing date+time
    games_in_window = []
    for game in candidate_games:
        try:
            game_start_utc = _game_start_utc(game)
            if game_start_utc is None:
                continue
            if now <= game_start_utc <= window_end:
                games_in_window.append((game, game_start_utc))
        except Exception as exc:
            logger.warning("[snapshot] Could not parse game datetime for game_id=%s: %s", game.id, exc)
            errors += 1

    if not games_in_window:
        logger.info("[snapshot] No upcoming games in window")
        return {"snapshotted": snapshotted, "skipped": skipped, "errors": errors}

    # Find which game_ids already have a prediction log
    candidate_ids = [game.id for game, _ in games_in_window]
    existing_ids_stmt = select(GamePredictionLog.game_id).where(
        GamePredictionLog.game_id.in_(candidate_ids)
    )
    existing_game_ids = set(pred_session.execute(existing_ids_stmt).scalars().all())

    new_rows = []
    for game, game_start_utc in games_in_window:
        if game.id in existing_game_ids:
            skipped += 1
            continue

        try:
            # Get org_id from home team
            team_row = hb_session.execute(
                select(Team).where(Team.id == game.home_team_id)
            ).scalar_one_or_none()
            org_id = team_row.org_id if team_row is not None else None

            home_skill = get_team_avg_skill(game.home_team_id, org_id)
            away_skill = get_team_avg_skill(game.visitor_team_id, org_id)

            if home_skill is not None and away_skill is not None:
                skill_differential = away_skill - home_skill
                if home_skill < away_skill:
                    predicted_winner_team_id = game.home_team_id
                elif away_skill < home_skill:
                    predicted_winner_team_id = game.visitor_team_id
                else:
                    predicted_winner_team_id = None
            else:
                skill_differential = None
                predicted_winner_team_id = None

            log_row = GamePredictionLog(
                game_id=game.id,
                org_id=org_id,
                game_date=game_start_utc.date(),
                game_scheduled_start=game_start_utc,
                home_team_id=game.home_team_id,
                away_team_id=game.visitor_team_id,
                home_avg_skill=home_skill,
                away_avg_skill=away_skill,
                skill_differential=skill_differential,
                predicted_winner_team_id=predicted_winner_team_id,
            )
            new_rows.append(log_row)

        except Exception as exc:
            logger.error("[snapshot] Error building log for game_id=%s: %s", game.id, exc)
            errors += 1

    # Commit all new rows in one batch
    if new_rows:
        try:
            pred_session.add_all(new_rows)
            pred_session.commit()
            snapshotted = len(new_rows)
        except Exception as exc:
            pred_session.rollback()
            logger.error("[snapshot] Batch commit failed: %s", exc)
            errors += len(new_rows)
            snapshotted = 0

    logger.info(
        "[snapshot] Done — snapshotted=%d skipped=%d errors=%d",
        snapshotted, skipped, errors,
    )
    return {"snapshotted": snapshotted, "skipped": skipped, "errors": errors}


def _game_start_utc(game) -> datetime | None:
    """
    Combine game.date and game.time, treat as Pacific time, return UTC datetime.
    Returns None if date or time is missing.
    """
    if game.date is None:
        return None

    game_time = getattr(game, "time", None)
    if game_time is None:
        # Default to midnight Pacific if no time set
        naive_dt = datetime(game.date.year, game.date.month, game.date.day, 0, 0, 0)
    else:
        naive_dt = datetime(
            game.date.year,
            game.date.month,
            game.date.day,
            game_time.hour,
            game_time.minute,
            game_time.second,
        )

    # Localize as Pacific, then convert to UTC
    pacific_dt = naive_dt.replace(tzinfo=_PACIFIC)
    return pacific_dt.astimezone(timezone.utc)

"""
Result grader — grades completed games and awards points.

Called by the background scheduler every GRADER_INTERVAL_MINUTES minutes.
Also callable manually for testing or backfilling.

Idempotent: safe to run multiple times; will not double-grade picks
(unique constraint on pred_results.pick_id prevents duplicates).
"""

import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import HBSession, PredSession
from app.models.pred_pick import PredPick
from app.models.pred_result import PredResult
from app.models.pred_league import PredLeague


FINAL_STATUSES = frozenset({"Final", "Final/OT", "Final/SO"})
VOID_STATUSES = frozenset({"Forfeit", "CANCELED"})
UPSET_SCALE = 0.5


def grade_completed_games() -> dict:
    """
    Main entry point for the background grader.

    Finds all ungraded PredPicks where the referenced game has reached a
    final or voided status, grades each one, and updates standings.

    Returns a summary dict: { "graded": int, "skipped": int, "errors": int }
    """
    pred_session = PredSession()
    summary = {"graded": 0, "skipped": 0, "errors": 0}

    # Find locked picks with no result yet
    stmt = (
        select(PredPick)
        .outerjoin(PredResult, PredPick.id == PredResult.pick_id)
        .where(
            PredResult.id.is_(None),
            PredPick.is_locked == True,  # noqa: E712
        )
    )
    ungraded_picks = pred_session.execute(stmt).scalars().all()

    if not ungraded_picks:
        return summary

    # Batch-load game data from hockey_blast
    game_ids = {p.game_id for p in ungraded_picks}
    game_cache = _load_games(game_ids)

    for pick in ungraded_picks:
        game = game_cache.get(pick.game_id)

        if game is None:
            summary["skipped"] += 1
            continue

        game_status = getattr(game, "status", None)
        if game_status not in FINAL_STATUSES | VOID_STATUSES:
            summary["skipped"] += 1
            continue

        try:
            league_stmt = select(PredLeague).where(PredLeague.id == pick.league_id)
            league = pred_session.execute(league_stmt).scalar_one_or_none()

            result = _grade_pick(pick, game, league)
            pred_session.add(result)

            # Update standings for this user in this league
            from app.services.standings_service import update_standings_for_result
            update_standings_for_result(result, pick, league, pred_session)

            summary["graded"] += 1

        except Exception as exc:
            # Log but don't abort the whole batch
            import traceback
            print(f"[grader] Error grading pick {pick.id}: {exc}")
            traceback.print_exc()
            summary["errors"] += 1

    try:
        pred_session.commit()
    except Exception as exc:
        pred_session.rollback()
        raise exc

    return summary


def _load_games(game_ids: set[int]) -> dict[int, object]:
    """Batch-load games from hockey_blast DB. Returns {game_id: game_obj}."""
    try:
        from hockey_blast_common_lib.models import Game
    except ImportError:
        return {}

    if not game_ids:
        return {}

    session = HBSession()
    stmt = select(Game).where(Game.id.in_(game_ids))
    games = session.execute(stmt).scalars().all()
    return {g.id: g for g in games}


def _get_winner(game, pred_session: Session) -> int | None:
    """
    Determine the winning team_id for a final game using goal counts.
    Returns None for ties (pick voided) or if data unavailable.
    """
    try:
        from hockey_blast_common_lib.models import Goal
    except ImportError:
        return None

    hb_session = HBSession()

    home_goals_stmt = select(Goal).where(
        Goal.game_id == game.id,
        Goal.team_id == game.home_team_id,
    )
    away_goals_stmt = select(Goal).where(
        Goal.game_id == game.id,
        Goal.team_id == game.away_team_id,
    )

    home_goals = len(hb_session.execute(home_goals_stmt).scalars().all())
    away_goals = len(hb_session.execute(away_goals_stmt).scalars().all())

    if home_goals > away_goals:
        return game.home_team_id
    elif away_goals > home_goals:
        return game.away_team_id
    return None  # Tie — void


def _grade_pick(pick: PredPick, game, league: PredLeague | None) -> PredResult:
    """
    Grade a single pick against the game result.
    Returns an unsaved PredResult object.
    """
    game_status = getattr(game, "status", "Unknown")

    result = PredResult(
        pick_id=pick.id,
        game_final_status=game_status,
        graded_at=datetime.now(timezone.utc),
    )

    # Voided game — zero points, pick excluded from accuracy stats
    if game_status in VOID_STATUSES:
        result.is_correct = False
        result.actual_winner_team_id = None
        result.base_points = 0
        result.upset_bonus_points = 0
        result.pre_multiplier_points = 0
        result.confidence_multiplier = pick.confidence
        result.total_points = 0
        return result

    # Determine winner
    actual_winner = _get_winner(game, None)
    result.actual_winner_team_id = actual_winner
    result.is_correct = actual_winner is not None and actual_winner == pick.picked_team_id
    result.confidence_multiplier = pick.confidence

    if not result.is_correct:
        result.base_points = 0
        result.upset_bonus_points = 0
        result.pre_multiplier_points = 0
        result.total_points = 0
        return result

    # Correct pick — compute points
    base = (league.correct_pick_base_points if league else 10)
    result.base_points = base

    upset_bonus = 0
    if (league is None or league.upset_bonus_enabled) and pick.skill_differential is not None:
        diff = float(pick.skill_differential)
        if diff > 0:
            upset_bonus = max(0, math.floor(diff * UPSET_SCALE))

    result.upset_bonus_points = upset_bonus
    result.pre_multiplier_points = base + upset_bonus

    use_multiplier = league is None or league.confidence_multiplier_enabled
    multiplier = pick.confidence if use_multiplier else 1
    result.total_points = result.pre_multiplier_points * multiplier

    return result


def compute_points(
    is_correct: bool,
    skill_differential: float | None,
    confidence: int,
    base_points: int = 10,
    upset_bonus_enabled: bool = True,
    confidence_multiplier_enabled: bool = True,
) -> dict:
    """
    Pure function: compute points breakdown.
    Useful for previewing projected points before pick submission.

    Returns: {
        "base_points": int,
        "upset_bonus_points": int,
        "pre_multiplier_points": int,
        "confidence_multiplier": int,
        "total_points": int,
    }
    """
    if not is_correct:
        return {
            "base_points": 0,
            "upset_bonus_points": 0,
            "pre_multiplier_points": 0,
            "confidence_multiplier": confidence,
            "total_points": 0,
        }

    upset_bonus = 0
    if upset_bonus_enabled and skill_differential is not None and skill_differential > 0:
        upset_bonus = max(0, math.floor(float(skill_differential) * UPSET_SCALE))

    pre_mult = base_points + upset_bonus
    multiplier = confidence if confidence_multiplier_enabled else 1
    total = pre_mult * multiplier

    return {
        "base_points": base_points,
        "upset_bonus_points": upset_bonus,
        "pre_multiplier_points": pre_mult,
        "confidence_multiplier": multiplier,
        "total_points": total,
    }


def compute_upset_bonus(skill_differential: float | None) -> int:
    """
    Compute the upset bonus for a given skill differential.
    skill_differential > 0 means you picked the weaker team (upset pick).
    """
    if skill_differential is None or skill_differential <= 0:
        return 0
    return max(0, math.floor(float(skill_differential) * UPSET_SCALE))

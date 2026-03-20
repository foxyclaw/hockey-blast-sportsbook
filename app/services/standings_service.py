"""
Standings service — maintains and refreshes PredLeagueStandings.

Two modes:
  1. Incremental update: update_standings_for_result() — called per result by grader
  2. Full recalculation: refresh_standings() — rebuilds from scratch (for repairs/backfills)
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.pred_league_standings import PredLeagueStandings
from app.models.pred_pick import PredPick
from app.models.pred_result import PredResult


VOID_STATUSES = frozenset({"Forfeit", "CANCELED"})


def update_standings_for_result(
    result: PredResult,
    pick: PredPick,
    league,
    pred_session: Session,
) -> PredLeagueStandings:
    """
    Incrementally update standings after a single result is graded.

    - Does NOT increment total_picks for void results (Forfeit/CANCELED).
    - Refreshes rank for all league members after updating.
    - Returns the updated PredLeagueStandings row (unsaved — caller commits).
    """
    stmt = select(PredLeagueStandings).where(
        PredLeagueStandings.user_id == pick.user_id,
        PredLeagueStandings.league_id == pick.league_id,
    )
    standings = pred_session.execute(stmt).scalar_one_or_none()

    if standings is None:
        standings = PredLeagueStandings(
            user_id=pick.user_id,
            league_id=pick.league_id,
            total_points=0,
            total_picks=0,
            correct_picks=0,
            upset_picks_correct=0,
            high_conf_correct=0,
            pick_accuracy=0.0,
        )
        pred_session.add(standings)

    is_void = result.game_final_status in VOID_STATUSES

    if not is_void:
        standings.total_picks += 1
        if result.is_correct:
            standings.correct_picks += 1

    standings.total_points += result.total_points

    if result.is_correct and pick.is_upset_pick:
        standings.upset_picks_correct += 1

    if result.is_correct and pick.confidence == 3:
        standings.high_conf_correct += 1

    # Recalculate accuracy (exclude void picks — only counted games)
    if standings.total_picks > 0:
        standings.pick_accuracy = round(
            (standings.correct_picks / standings.total_picks) * 100, 2
        )
    else:
        standings.pick_accuracy = 0.0

    standings.last_updated_at = datetime.now(timezone.utc)

    # Refresh ranks for the whole league
    _refresh_ranks(pick.league_id, pred_session)

    return standings


def refresh_standings(league_id: int, pred_session: Session) -> None:
    """
    Full recalculation of standings for a league from scratch.
    Rebuilds all PredLeagueStandings rows from PredResult data.

    Use this:
    - After data corrections
    - When you suspect incremental updates got out of sync
    - For admin tools

    This does NOT clear existing standings rows; it updates them in-place.
    """
    # Get all graded results for picks in this league
    stmt = (
        select(
            PredPick.user_id,
            func.sum(PredResult.total_points).label("total_points"),
            func.count(PredResult.id).label("graded_count"),
            func.sum(
                # Only count non-void picks in total_picks
                (PredResult.game_final_status.not_in(list(VOID_STATUSES))).cast(
                    pred_session.bind.dialect.colspecs.get(type(1), type(1))
                )
            ).label("counted_picks"),
            func.sum(
                (PredResult.is_correct == True).cast(  # noqa: E712
                    pred_session.bind.dialect.colspecs.get(type(1), type(1))
                )
            ).label("correct_picks"),
        )
        .join(PredResult, PredPick.id == PredResult.pick_id)
        .where(PredPick.league_id == league_id)
        .group_by(PredPick.user_id)
    )

    # Note: The above uses dialect-specific casting which may not be portable.
    # For robustness, use the simpler per-user loop approach:
    _refresh_standings_loop(league_id, pred_session)


def _refresh_standings_loop(league_id: int, pred_session: Session) -> None:
    """
    Recalculate standings by iterating per user. Less efficient but portable.
    """
    # Get all distinct user_ids who have picks in this league
    user_ids_stmt = (
        select(PredPick.user_id)
        .where(PredPick.league_id == league_id)
        .distinct()
    )
    user_ids = pred_session.execute(user_ids_stmt).scalars().all()

    for user_id in user_ids:
        # Get all results for this user in this league
        results_stmt = (
            select(PredResult, PredPick)
            .join(PredPick, PredResult.pick_id == PredPick.id)
            .where(
                PredPick.user_id == user_id,
                PredPick.league_id == league_id,
            )
        )
        rows = pred_session.execute(results_stmt).all()

        total_points = 0
        total_picks = 0
        correct_picks = 0
        upset_picks_correct = 0
        high_conf_correct = 0

        for result, pick in rows:
            is_void = result.game_final_status in VOID_STATUSES
            total_points += result.total_points
            if not is_void:
                total_picks += 1
                if result.is_correct:
                    correct_picks += 1
            if result.is_correct and pick.is_upset_pick:
                upset_picks_correct += 1
            if result.is_correct and pick.confidence == 3:
                high_conf_correct += 1

        accuracy = round((correct_picks / total_picks) * 100, 2) if total_picks > 0 else 0.0

        # Upsert standings row
        standings_stmt = select(PredLeagueStandings).where(
            PredLeagueStandings.user_id == user_id,
            PredLeagueStandings.league_id == league_id,
        )
        standings = pred_session.execute(standings_stmt).scalar_one_or_none()

        if standings is None:
            standings = PredLeagueStandings(user_id=user_id, league_id=league_id)
            pred_session.add(standings)

        standings.total_points = total_points
        standings.total_picks = total_picks
        standings.correct_picks = correct_picks
        standings.upset_picks_correct = upset_picks_correct
        standings.high_conf_correct = high_conf_correct
        standings.pick_accuracy = accuracy
        standings.last_updated_at = datetime.now(timezone.utc)

    _refresh_ranks(league_id, pred_session)


def _refresh_ranks(league_id: int, pred_session: Session) -> None:
    """
    Recompute rank for all members in a league, ordered by total_points DESC.
    Tied scores get the same rank (dense ranking).
    """
    stmt = (
        select(PredLeagueStandings)
        .where(PredLeagueStandings.league_id == league_id)
        .order_by(PredLeagueStandings.total_points.desc())
    )
    rows = pred_session.execute(stmt).scalars().all()

    rank = 1
    prev_points = None
    for i, row in enumerate(rows):
        if prev_points is not None and row.total_points < prev_points:
            rank = i + 1
        row.rank = rank
        prev_points = row.total_points

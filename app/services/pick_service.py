"""
Pick service — submit, validate, update, and retract picks.

Key operations:
    submit_pick()     — create or update a pick (validates lock, team, league membership)
    retract_pick()    — delete a pick (only if still unlocked)
    validate_pick_window() — alias for lock_checker.is_game_pickable()
    lock_check()      — raise PickLockError if game is locked
"""

import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pred_pick import PredPick
from app.models.pred_league import PredLeague
from app.models.pred_league_member import PredLeagueMember
from app.models.pred_user import PredUser
from app.services.lock_checker import is_game_pickable, get_lock_deadline
from app.services.skill_snapshot import get_game_skill_snapshot, compute_pick_skill_fields


class PickError(Exception):
    """Base class for pick submission errors."""

    def __init__(self, code: str, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


class PickLockedError(PickError):
    def __init__(self, reason: str = "Pick window has closed"):
        super().__init__("PICK_LOCKED", reason, 409)


class InvalidTeamError(PickError):
    def __init__(self):
        super().__init__("INVALID_TEAM", "Picked team is not in this game", 400)


class NotLeagueMemberError(PickError):
    def __init__(self):
        super().__init__(
            "NOT_MEMBER", "You are not a member of this league", 403
        )


class GameNotFoundError(PickError):
    def __init__(self):
        super().__init__("NOT_FOUND", "Game not found", 404)


def validate_pick_window(game_id: int) -> None:
    """Raise PickLockedError if the game is not pickable."""
    ok, reason = is_game_pickable(game_id)
    if not ok:
        raise PickLockedError(reason)


def lock_check(game_id: int) -> None:
    """Alias for validate_pick_window. Raises PickLockedError if locked."""
    validate_pick_window(game_id)


def _get_game_teams(game_id: int) -> tuple[int, int, datetime | None]:
    """
    Return (home_team_id, away_team_id, scheduled_start) from hockey_blast DB.
    Raises GameNotFoundError if not found.
    """
    try:
        from hockey_blast_common_lib.models import Game
        from app.db import HBSession

        session = HBSession()
        stmt = select(Game).where(Game.id == game_id)
        game = session.execute(stmt).scalar_one_or_none()
        if game is None:
            raise GameNotFoundError()

        # Combine separate date + time columns
        game_date = getattr(game, "date", None)
        game_time = getattr(game, "time", None)
        if game_date is not None:
            if game_time is not None:
                scheduled = datetime.combine(game_date, game_time)
            else:
                scheduled = datetime(game_date.year, game_date.month, game_date.day)
        else:
            scheduled = None

        return game.home_team_id, game.visitor_team_id, scheduled

    except ImportError:
        # No hockey_blast_common_lib — tests use mocked values
        raise GameNotFoundError()


def _assert_league_member(user_id: int, league_id: int, pred_session: Session) -> None:
    """Raise NotLeagueMemberError if user is not an active member of the league."""
    stmt = select(PredLeagueMember).where(
        PredLeagueMember.user_id == user_id,
        PredLeagueMember.league_id == league_id,
        PredLeagueMember.is_active == True,  # noqa: E712
    )
    member = pred_session.execute(stmt).scalar_one_or_none()
    if member is None:
        raise NotLeagueMemberError()


def submit_pick(
    user: PredUser,
    game_id: int,
    league_id: int,
    picked_team_id: int,
    confidence: int,
    pred_session: Session,
    wager: int | None = None,
) -> PredPick:
    """
    Submit or update a pick.

    Steps:
      1. Validate pick window (game must be pickable)
      2. Validate user is in the league
      3. Validate picked_team_id is home or away
      4. Validate wager (if provided)
      5. Snapshot skill data
      6. Upsert PredPick

    Returns the PredPick (not yet committed — caller commits).
    """
    # Step 1: Lock check
    validate_pick_window(game_id)

    # Step 2: League membership
    _assert_league_member(user.id, league_id, pred_session)

    # Step 3: Get game details and validate team
    home_team_id, away_team_id, scheduled_start = _get_game_teams(game_id)
    if picked_team_id not in (home_team_id, away_team_id):
        raise InvalidTeamError()

    # Step 4: Validate and enforce wager (required, min 10)
    # Reload user from pred_session to ensure we have the latest balance
    db_user = pred_session.get(PredUser, user.id)
    if db_user is None:
        raise PickError("NOT_FOUND", "User not found", 404)

    if db_user.balance < 10:
        raise PickError("INSUFFICIENT_BALANCE", "Insufficient balance — need at least 10 pts to place a pick", 400)

    # Default wager if not provided or too low
    if wager is None or wager < 10:
        wager = 10
    max_wager = min(500, db_user.balance // 2) if db_user.balance > 20 else 10
    wager = min(wager, max_wager)

    # Step 5: Skill snapshot
    snapshot = get_game_skill_snapshot(game_id)
    skill_fields = compute_pick_skill_fields(
        picked_team_id=picked_team_id,
        home_team_id=home_team_id,
        visitor_team_id=away_team_id,
        home_skill=snapshot["home_team_avg_skill"],
        visitor_skill=snapshot["away_team_avg_skill"],
    )

    # Compute odds and derived wager fields
    from app.services.odds_service import get_pick_odds
    odds = get_pick_odds(
        picked_team_id=picked_team_id,
        home_team_id=home_team_id,
        home_avg_skill=snapshot["home_team_avg_skill"],
        visitor_avg_skill=snapshot["away_team_avg_skill"],
    )
    effective_wager = wager * confidence
    potential_payout = int(effective_wager * odds)

    # Step 6: Upsert
    stmt = select(PredPick).where(
        PredPick.user_id == db_user.id,
        PredPick.game_id == game_id,
        PredPick.league_id == league_id,
    )
    existing = pred_session.execute(stmt).scalar_one_or_none()

    if existing is not None:
        # Update existing pick — refund old effective_wager, deduct new one
        if existing.is_locked:
            raise PickLockedError("This pick is already locked")

        # Refund old effective wager if it was deducted
        old_effective_wager = existing.effective_wager or 0
        db_user.balance += old_effective_wager

        # Check balance again after refund
        if db_user.balance < effective_wager:
            # Undo refund and raise error
            db_user.balance -= old_effective_wager
            raise PickError("INSUFFICIENT_BALANCE", "Insufficient balance for this wager", 400)

        existing.picked_team_id = picked_team_id
        existing.confidence = confidence
        existing.home_team_id = home_team_id
        existing.away_team_id = away_team_id
        existing.home_team_avg_skill = snapshot["home_team_avg_skill"]
        existing.away_team_avg_skill = snapshot["away_team_avg_skill"]
        existing.picked_team_avg_skill = skill_fields["picked_team_avg_skill"]
        existing.opponent_avg_skill = skill_fields["opponent_avg_skill"]
        existing.skill_differential = skill_fields["skill_differential"]
        existing.is_upset_pick = skill_fields["is_upset_pick"]
        existing.wager = wager
        existing.odds_at_pick = odds
        existing.effective_wager = effective_wager
        existing.potential_payout = potential_payout
        pick = existing
    else:
        # Create new pick
        pick = PredPick(
            user_id=db_user.id,
            league_id=league_id,
            game_id=game_id,
            game_scheduled_start=scheduled_start,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            picked_team_id=picked_team_id,
            confidence=confidence,
            home_team_avg_skill=snapshot["home_team_avg_skill"],
            away_team_avg_skill=snapshot["away_team_avg_skill"],
            picked_team_avg_skill=skill_fields["picked_team_avg_skill"],
            opponent_avg_skill=skill_fields["opponent_avg_skill"],
            skill_differential=skill_fields["skill_differential"],
            is_upset_pick=skill_fields["is_upset_pick"],
            wager=wager,
            odds_at_pick=odds,
            effective_wager=effective_wager,
            potential_payout=potential_payout,
        )
        pred_session.add(pick)

    # Deduct effective wager from user balance immediately
    db_user.balance -= effective_wager

    return pick


def retract_pick(user: PredUser, pick_id: int, pred_session: Session) -> None:
    """
    Retract (delete) a pick if the game is still unlocked.

    Raises:
        PickLockedError  — if the game has started
        PickError        — if pick not found or not owned by user
    """
    pick = pred_session.get(PredPick, pick_id)
    if pick is None or pick.user_id != user.id:
        raise PickError("NOT_FOUND", "Pick not found", 404)

    if pick.is_locked:
        raise PickLockedError("Cannot retract a locked pick")

    # Re-check game lock just to be safe
    ok, reason = is_game_pickable(pick.game_id)
    if not ok:
        raise PickLockedError(reason)

    pred_session.delete(pick)


def compute_projected_points(
    pick: PredPick, league: PredLeague
) -> dict[str, int]:
    """
    Return projected point totals for a pick in a league.

    Returns: { "correct": int, "wrong": int }
    """
    base = league.correct_pick_base_points

    upset_bonus = 0
    if league.upset_bonus_enabled and pick.skill_differential is not None:
        diff = float(pick.skill_differential)
        if diff > 0:
            upset_bonus = max(0, math.floor(diff * 0.5))

    pre_mult = base + upset_bonus
    multiplier = pick.confidence if league.confidence_multiplier_enabled else 1
    total = pre_mult * multiplier

    return {"correct": total, "wrong": 0}

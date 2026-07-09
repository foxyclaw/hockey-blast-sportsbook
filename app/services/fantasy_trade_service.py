"""
fantasy_trade_service — manages mid-season trade rounds for active leagues.

Flow:
  1. League creator initiates a round (initiate_trade_round).
  2. Turn order = managers by ascending fantasy points (lowest FP goes first).
  3. On their turn a manager either:
       - swaps: release one rostered player, acquire one available player of the
         SAME type (skater/goalie/ref)  → make_trade()
       - skips: keep their team                                  → skip_turn()
       - misses: deadline passes; advance_trade_round() marks them missed and
         moves on. Missed managers get a SECOND pass (round-robin) after everyone
         else has gone in pass 1.
  4. When pass-1 and pass-2 turns are all resolved, the round completes.

Point attribution: FULL REATTRIBUTION. When a player is traded, all of their
existing fantasy_game_scores rows in this league are reassigned to the new owner,
so the new owner gets the player's entire season production and standings
recompute on the fly.

"Available" players = current-season-eligible (league.hb_season_id) players who
are NOT currently on any roster in this league. This naturally includes both
players who newly appeared this season and players released earlier in the round.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import PredSession
from app.models.fantasy_league import FantasyLeague
from app.models.fantasy_manager import FantasyManager
from app.models.fantasy_roster import FantasyRoster
from app.models.fantasy_game_scores import FantasyGameScores
from app.models.fantasy_trade_round import (
    FantasyTradeRound,
    TRADE_ROUND_ACTIVE,
    TRADE_ROUND_COMPLETED,
)
from app.models.fantasy_trade_turn import FantasyTradeTurn

logger = logging.getLogger(__name__)


# ── Round lifecycle ────────────────────────────────────────────────────────────

def initiate_trade_round(league_id: int, created_by: int, pick_hours: int = 24) -> dict:
    """
    Create a new trade round for an active league and build pass-1 turns in
    ascending fantasy-points order (lowest FP first). Sets the deadline on the
    first turn and notifies that manager.

    Raises ValueError on validation failure.
    """
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None:
        raise ValueError("League not found")
    if league.status != "active":
        raise ValueError(f"Trades are only allowed while the league is active (status={league.status})")

    # Only one open round at a time.
    existing = pred.execute(
        select(FantasyTradeRound).where(
            FantasyTradeRound.league_id == league_id,
            FantasyTradeRound.status == TRADE_ROUND_ACTIVE,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("A trade round is already in progress for this league")

    managers = pred.execute(
        select(FantasyManager).where(FantasyManager.league_id == league_id)
    ).scalars().all()
    if len(managers) < 2:
        raise ValueError("Need at least 2 managers to run a trade round")

    rnd = FantasyTradeRound(
        league_id=league_id,
        status=TRADE_ROUND_ACTIVE,
        pick_hours=max(1, int(pick_hours or 24)),
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    pred.add(rnd)
    pred.commit()

    # Turn order: ascending fantasy points (lowest first). Managers with no
    # standings row count as 0 points (they go first, ties broken by user_id).
    ordered_user_ids = _managers_by_ascending_fp(league_id, managers, pred)

    turns = []
    for order, user_id in enumerate(ordered_user_ids, 1):
        turns.append({
            "round_id": rnd.id,
            "league_id": league_id,
            "user_id": user_id,
            "turn_order": order,
            "pass_number": 1,
        })
    pred.execute(pg_insert(FantasyTradeTurn).values(turns).on_conflict_do_nothing())
    pred.commit()

    _activate_next_turn(rnd.id, pred)
    return rnd.to_dict()


def _managers_by_ascending_fp(league_id: int, managers, pred) -> list[int]:
    """Return manager user_ids ordered by ascending total fantasy points."""
    from app.models.fantasy_standings import FantasyStandings
    standings = pred.execute(
        select(FantasyStandings.user_id, FantasyStandings.total_points)
        .where(FantasyStandings.league_id == league_id)
    ).all()
    fp_map = {r.user_id: float(r.total_points or 0) for r in standings}
    # lowest FP first; stable tiebreak by user_id for determinism
    return sorted(
        (m.user_id for m in managers),
        key=lambda uid: (fp_map.get(uid, 0.0), uid),
    )


def _current_turn(round_id: int, pred):
    """Return the active (deadline-set, unresolved) turn for a round, or None."""
    return pred.execute(
        select(FantasyTradeTurn)
        .where(
            FantasyTradeTurn.round_id == round_id,
            FantasyTradeTurn.deadline.is_not(None),
            FantasyTradeTurn.acted_at.is_(None),
            FantasyTradeTurn.is_skipped == False,  # noqa: E712
            FantasyTradeTurn.is_missed == False,  # noqa: E712
        )
        .order_by(FantasyTradeTurn.pass_number.asc(), FantasyTradeTurn.turn_order.asc())
        .limit(1)
    ).scalar_one_or_none()


def _activate_next_turn(round_id: int, pred) -> None:
    """
    Find the next unresolved turn with no deadline yet, set its deadline, and
    notify the manager. If pass 1 is exhausted, build pass 2 (second chance) for
    managers who missed pass 1. If nothing remains, complete the round.
    """
    rnd = pred.get(FantasyTradeRound, round_id)
    if rnd is None or rnd.status != TRADE_ROUND_ACTIVE:
        return

    # If a turn is already active, do nothing (someone is on the clock).
    if _current_turn(round_id, pred) is not None:
        return

    nxt = _next_unstarted_turn(round_id, pred)
    if nxt is None:
        # Pass 1 (and any existing pass 2) exhausted. Try to build pass 2.
        if not _build_second_chance_pass(round_id, pred):
            _complete_round(round_id, pred)
            return
        nxt = _next_unstarted_turn(round_id, pred)
        if nxt is None:
            _complete_round(round_id, pred)
            return

    nxt.deadline = datetime.now(timezone.utc) + timedelta(hours=rnd.pick_hours)
    pred.commit()
    _notify_turn(nxt.user_id, rnd.league_id, nxt.deadline, pred)


def _next_unstarted_turn(round_id: int, pred):
    """Next turn that has not been given a deadline and is not resolved."""
    return pred.execute(
        select(FantasyTradeTurn)
        .where(
            FantasyTradeTurn.round_id == round_id,
            FantasyTradeTurn.deadline.is_(None),
            FantasyTradeTurn.acted_at.is_(None),
            FantasyTradeTurn.is_skipped == False,  # noqa: E712
            FantasyTradeTurn.is_missed == False,  # noqa: E712
        )
        .order_by(FantasyTradeTurn.pass_number.asc(), FantasyTradeTurn.turn_order.asc())
        .limit(1)
    ).scalar_one_or_none()


def _build_second_chance_pass(round_id: int, pred) -> bool:
    """
    Create pass-2 turns for managers who MISSED their pass-1 turn (round-robin
    second chance). Returns True if any were created. Idempotent: won't duplicate
    pass-2 turns that already exist.
    """
    missed = pred.execute(
        select(FantasyTradeTurn)
        .where(
            FantasyTradeTurn.round_id == round_id,
            FantasyTradeTurn.pass_number == 1,
            FantasyTradeTurn.is_missed == True,  # noqa: E712
        )
        .order_by(FantasyTradeTurn.turn_order.asc())
    ).scalars().all()
    if not missed:
        return False

    already = {
        t.user_id
        for t in pred.execute(
            select(FantasyTradeTurn).where(
                FantasyTradeTurn.round_id == round_id,
                FantasyTradeTurn.pass_number == 2,
            )
        ).scalars().all()
    }

    new_turns = []
    order = 1
    for t in missed:
        if t.user_id in already:
            continue
        new_turns.append({
            "round_id": round_id,
            "league_id": t.league_id,
            "user_id": t.user_id,
            "turn_order": order,
            "pass_number": 2,
        })
        order += 1

    if not new_turns:
        return False
    pred.execute(pg_insert(FantasyTradeTurn).values(new_turns).on_conflict_do_nothing())
    pred.commit()
    logger.info("[trade] round=%d built second-chance pass for %d managers", round_id, len(new_turns))
    return True


def _complete_round(round_id: int, pred) -> None:
    rnd = pred.get(FantasyTradeRound, round_id)
    if rnd and rnd.status == TRADE_ROUND_ACTIVE:
        rnd.status = TRADE_ROUND_COMPLETED
        rnd.completed_at = datetime.now(timezone.utc)
        pred.commit()
        logger.info("[trade] round=%d completed", round_id)


def advance_trade_round(round_id: int) -> None:
    """
    Background-job entrypoint: if the current turn's deadline has passed, mark it
    missed and activate the next turn. Safe to call repeatedly.
    """
    pred = PredSession()
    rnd = pred.get(FantasyTradeRound, round_id)
    if rnd is None or rnd.status != TRADE_ROUND_ACTIVE:
        return

    now = datetime.now(timezone.utc)
    current = _current_turn(round_id, pred)
    if current is None:
        # No active turn — try to advance (e.g. round just created, or stalled).
        _activate_next_turn(round_id, pred)
        return
    if current.deadline and current.deadline > now:
        return  # still on the clock

    # Deadline passed. First try to auto-trade on the manager's behalf: if they
    # have a dead-weight skater (0 fantasy points), swap it for the best available
    # skater. If that succeeds the turn auto-completes; otherwise mark it missed
    # (pass-1 missers still get a pass-2 second chance).
    if _try_auto_trade_for_expired_turn(league_id=rnd.league_id, round_id=round_id,
                                        turn=current, pred=pred):
        return  # make_trade already advanced to the next turn

    current.is_missed = True
    current.acted_at = None
    pred.commit()
    logger.info("[trade] round=%d user=%d missed turn (pass %d)",
                round_id, current.user_id, current.pass_number)
    _activate_next_turn(round_id, pred)


# Role → the pool's role-specific fantasy-points key (what the acquired player adds).
_ROLE_FP_KEY = {
    "skater": "fantasy_points_skater",
    "goalie": "fantasy_points_goalie",
    "ref": "fantasy_points_ref",
}


def _try_auto_trade_for_expired_turn(league_id: int, round_id: int, turn, pred) -> bool:
    """
    Auto-trade for a manager whose turn expired: if they hold any player with zero
    fantasy points, release it and acquire the best available replacement OF THE
    SAME ROLE (skater→skater, goalie→goalie, ref→ref).

    Because releasing a zero-point player adds exactly the acquired player's
    points, we evaluate every role the manager has a zero-point player in and pick
    the single swap that ADDS THE MOST POINTS overall. Only performed when it's a
    real upgrade (acquired player has > 0 points).

    Returns True if an auto-trade was performed (turn complete), else False (caller
    marks the turn missed). Notifies the manager like the auto-draft flow.
    """
    user_id = turn.user_id

    # This manager's roster with role flags.
    roster = pred.execute(
        select(FantasyRoster.hb_human_id, FantasyRoster.is_goalie, FantasyRoster.is_ref)
        .where(FantasyRoster.league_id == league_id, FantasyRoster.user_id == user_id)
    ).all()
    if not roster:
        return False

    # Points each rostered player has earned in this league.
    ids = [r.hb_human_id for r in roster]
    pts_rows = pred.execute(
        select(
            FantasyGameScores.hb_human_id,
            func.coalesce(func.sum(FantasyGameScores.points), 0).label("pts"),
        )
        .where(FantasyGameScores.league_id == league_id, FantasyGameScores.hb_human_id.in_(ids))
        .group_by(FantasyGameScores.hb_human_id)
    ).all()
    pts_map = {r.hb_human_id: float(r.pts or 0) for r in pts_rows}

    # Zero-point players grouped by role. Deterministic release pick per role:
    # lowest hb_human_id.
    zero_by_role: dict[str, int] = {}
    for r in roster:
        if pts_map.get(r.hb_human_id, 0.0) != 0.0:
            continue
        role = _player_type(r.is_goalie, r.is_ref)
        if role not in zero_by_role or r.hb_human_id < zero_by_role[role]:
            zero_by_role[role] = r.hb_human_id
    if not zero_by_role:
        return False

    # For each role with a zero-point player, find the best available replacement
    # of that role; keep the swap that adds the most points overall.
    best_swap = None  # (points_added, release_id, acquire_id, role, acquire_name)
    for role, release_id in zero_by_role.items():
        available = get_available_players(league_id, of_type=role)
        if not available:
            continue
        fp_key = _ROLE_FP_KEY[role]
        cand = max(available, key=lambda p: float(p.get(fp_key, 0) or 0))
        gain = float(cand.get(fp_key, 0) or 0)
        if gain <= 0:
            continue  # no upgrade for this role
        if best_swap is None or gain > best_swap[0]:
            name = f"{cand.get('first_name', '')} {cand.get('last_name', '')}".strip()
            best_swap = (gain, release_id, cand["hb_human_id"], role, name)

    if best_swap is None:
        return False  # no positive-scoring replacement in any role — mark missed

    _gain, release_id, acquire_id, role, _name = best_swap
    try:
        make_trade(league_id, user_id, release_id, acquire_id)
    except ValueError as e:
        logger.warning("[trade] auto-trade failed for league=%d user=%d: %s",
                       league_id, user_id, e)
        return False

    logger.info("[trade] round=%d user=%d AUTO-traded (%s) release=%d acquire=%d (+%.1f pts)",
                round_id, user_id, role, release_id, acquire_id, _gain)
    _notify_auto_trade(user_id, league_id, release_id, acquire_id, pred)
    return True


def advance_active_trade_rounds() -> dict:
    """Scheduler hook: advance every active trade round. Returns a summary."""
    pred = PredSession()
    summary = {"rounds": 0, "advanced": 0}
    rounds = pred.execute(
        select(FantasyTradeRound).where(FantasyTradeRound.status == TRADE_ROUND_ACTIVE)
    ).scalars().all()
    for rnd in rounds:
        summary["rounds"] += 1
        try:
            advance_trade_round(rnd.id)
            summary["advanced"] += 1
        except Exception as e:
            logger.warning("[trade] advance failed for round=%d: %s", rnd.id, e)
    return summary


# ── Manager actions ──────────────────────────────────────────────────────────

def make_trade(league_id: int, user_id: int, release_hb_human_id: int,
               acquire_hb_human_id: int) -> dict:
    """
    Execute a one-for-one swap on the calling manager's turn:
      - release `release_hb_human_id` (must be on the manager's roster)
      - acquire `acquire_hb_human_id` (must be available + same type as released)
    Reattributes the acquired player's existing scores to the new owner and
    recomputes standings. Ends the manager's turn.

    Raises ValueError on validation failure.
    """
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None:
        raise ValueError("League not found")

    rnd = _active_round(league_id, pred)
    if rnd is None:
        raise ValueError("No trade round is in progress")

    current = _current_turn(rnd.id, pred)
    if current is None:
        raise ValueError("No active turn right now")
    if current.user_id != user_id:
        raise ValueError("It is not your turn to trade")

    # Released player must be on this manager's roster.
    released = pred.execute(
        select(FantasyRoster).where(
            FantasyRoster.league_id == league_id,
            FantasyRoster.user_id == user_id,
            FantasyRoster.hb_human_id == release_hb_human_id,
        )
    ).scalar_one_or_none()
    if released is None:
        raise ValueError("You can only release a player on your own roster")

    # No-op swap (release == acquire) is treated as a skip.
    if release_hb_human_id == acquire_hb_human_id:
        return skip_turn(league_id, user_id)

    # Acquired player must NOT currently be on any roster in this league.
    taken = pred.execute(
        select(FantasyRoster).where(
            FantasyRoster.league_id == league_id,
            FantasyRoster.hb_human_id == acquire_hb_human_id,
        )
    ).scalar_one_or_none()
    if taken is not None:
        raise ValueError("That player is already on a team in this league")

    # Acquired player must be available + the SAME type as the released player.
    released_type = _player_type(released.is_goalie, released.is_ref)
    available = get_available_players(league_id, of_type=released_type)
    cand = next((p for p in available if p["hb_human_id"] == acquire_hb_human_id), None)
    if cand is None:
        raise ValueError(
            f"That player is not available as a {released_type} this season"
        )

    now = datetime.now(timezone.utc)

    # Swap the roster row: keep the row, change identity + role flags + provenance.
    released.hb_human_id = acquire_hb_human_id
    released.is_goalie = released_type == "goalie"
    released.is_ref = released_type == "ref"
    released.round_picked = None
    released.pick_number = None
    released.drafted_at = now
    pred.commit()

    # SCORE + REATTRIBUTE the acquired player.
    #
    # score_game() only ever creates rows for players who were rostered at scoring
    # time, so a free agent picked up in a trade (never previously rostered in this
    # league) has NO score rows to reattribute. Now that the roster swap above has
    # made them rostered under the new owner, re-score the league's already-scored
    # games so their historical games are recorded for this owner (cheap: only the
    # games the league has already scored). This creates rows for a never-scored
    # acquisition and refreshes rows for a previously-rostered one.
    try:
        from app.services.fantasy_scoring_service import backfill_scoring_after_trade
        backfill_scoring_after_trade(league_id)
    except Exception as e:
        logger.warning("[trade] backfill scoring failed for league=%d acquire=%d: %s",
                       league_id, acquire_hb_human_id, e)

    # Belt-and-suspenders: reassign any remaining rows for the acquired player to
    # the new owner (covers score rows in games outside the re-scored set).
    _reassign_player_scores(league_id, acquire_hb_human_id, user_id, pred)

    # Record the turn outcome.
    current.released_hb_human_id = release_hb_human_id
    current.acquired_hb_human_id = acquire_hb_human_id
    current.acted_at = now
    pred.commit()

    recompute_standings(league_id, pred)
    _activate_next_turn(rnd.id, pred)

    logger.info("[trade] league=%d user=%d released=%d acquired=%d",
                league_id, user_id, release_hb_human_id, acquire_hb_human_id)
    return current.to_dict()


def skip_turn(league_id: int, user_id: int) -> dict:
    """Manager keeps their team and ends their turn."""
    pred = PredSession()
    rnd = _active_round(league_id, pred)
    if rnd is None:
        raise ValueError("No trade round is in progress")

    current = _current_turn(rnd.id, pred)
    if current is None:
        raise ValueError("No active turn right now")
    if current.user_id != user_id:
        raise ValueError("It is not your turn to trade")

    current.is_skipped = True
    current.acted_at = datetime.now(timezone.utc)
    pred.commit()
    logger.info("[trade] league=%d user=%d skipped", league_id, user_id)
    _activate_next_turn(rnd.id, pred)
    return current.to_dict()


# ── Queries / helpers ──────────────────────────────────────────────────────────

def _active_round(league_id: int, pred):
    return pred.execute(
        select(FantasyTradeRound).where(
            FantasyTradeRound.league_id == league_id,
            FantasyTradeRound.status == TRADE_ROUND_ACTIVE,
        )
    ).scalar_one_or_none()


def _player_type(is_goalie: bool, is_ref: bool) -> str:
    if is_goalie:
        return "goalie"
    if is_ref:
        return "ref"
    return "skater"


def get_available_players(league_id: int, of_type: str | None = None) -> list[dict]:
    """
    Players eligible to be acquired: current-season pool (league.hb_season_id)
    minus everyone currently rostered in this league. Optionally filter to a
    single type ('skater' | 'goalie' | 'ref').
    """
    from app.services.fantasy_pool_service import get_player_pool
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None:
        return []

    pool = get_player_pool(
        league.level_id,
        org_id=league.org_id,
        league_id=league.hb_league_id,
        # CURRENT season (play season), NOT draft_season_id — this is the key
        # difference from the draft pool: new this-season players become available.
        season_id=league.hb_season_id,
        min_games=league.min_games_played or 1,
    )

    rostered = set(pred.execute(
        select(FantasyRoster.hb_human_id).where(FantasyRoster.league_id == league_id)
    ).scalars().all())

    if of_type == "goalie":
        candidates = pool["goalies"]
    elif of_type == "ref":
        candidates = pool.get("refs", [])
    elif of_type == "skater":
        candidates = pool["skaters"]
    else:
        candidates = pool["players"]

    return [p for p in candidates if p["hb_human_id"] not in rostered]


def _reassign_player_scores(league_id: int, hb_human_id: int, new_user_id: int, pred) -> None:
    """Reattribute all of a player's scores in this league to the new owner."""
    pred.execute(
        FantasyGameScores.__table__.update()
        .where(
            FantasyGameScores.league_id == league_id,
            FantasyGameScores.hb_human_id == hb_human_id,
        )
        .values(user_id=new_user_id)
    )
    pred.commit()


def recompute_standings(league_id: int, pred=None) -> None:
    """
    Recompute standings from CURRENT roster ownership (full-reattribution model).

    Team total = sum of fantasy_game_scores.points for players currently on the
    manager's roster. Using current ownership (rather than the frozen user_id on
    score rows) means a released player's points stop counting for the old owner
    and an acquired player's full history counts for the new owner.
    """
    from app.models.fantasy_standings import FantasyStandings
    if pred is None:
        pred = PredSession()

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    managers = pred.execute(
        select(FantasyManager.user_id).where(FantasyManager.league_id == league_id)
    ).scalars().all()

    # Sum points per current-owner by joining scores to the live roster.
    total_rows = pred.execute(
        select(
            FantasyRoster.user_id,
            func.coalesce(func.sum(FantasyGameScores.points), 0).label("total"),
        )
        .select_from(FantasyRoster)
        .join(
            FantasyGameScores,
            (FantasyGameScores.league_id == FantasyRoster.league_id)
            & (FantasyGameScores.hb_human_id == FantasyRoster.hb_human_id),
        )
        .where(FantasyRoster.league_id == league_id)
        .group_by(FantasyRoster.user_id)
    ).all()
    total_map = {r.user_id: float(r.total or 0) for r in total_rows}

    # Week points — restrict to games in the last 7 days (by HB game date).
    week_map: dict[int, float] = {}
    try:
        from app.db import HBSession
        from sqlalchemy import text as sa_text
        hb = HBSession()
        game_ids = pred.execute(
            select(FantasyGameScores.game_id)
            .where(FantasyGameScores.league_id == league_id)
            .distinct()
        ).scalars().all()
        recent_ids: set[int] = set()
        if game_ids:
            ids_sql = ",".join(str(int(g)) for g in game_ids)
            recent = hb.execute(sa_text(
                f"SELECT id FROM games WHERE id IN ({ids_sql}) AND date >= :cutoff"
            ), {"cutoff": week_ago.date()}).fetchall()
            recent_ids = {r.id for r in recent}
        if recent_ids:
            week_rows = pred.execute(
                select(
                    FantasyRoster.user_id,
                    func.coalesce(func.sum(FantasyGameScores.points), 0).label("wtotal"),
                )
                .select_from(FantasyRoster)
                .join(
                    FantasyGameScores,
                    (FantasyGameScores.league_id == FantasyRoster.league_id)
                    & (FantasyGameScores.hb_human_id == FantasyRoster.hb_human_id),
                )
                .where(
                    FantasyRoster.league_id == league_id,
                    FantasyGameScores.game_id.in_(recent_ids),
                )
                .group_by(FantasyRoster.user_id)
            ).all()
            week_map = {r.user_id: float(r.wtotal or 0) for r in week_rows}
    except Exception as e:
        logger.warning("[trade] week_points recompute failed: %s", e)
        try:
            hb.rollback()
        except Exception:
            pass

    # Rank all managers (include those with 0 points / empty rosters).
    all_users = set(managers) | set(total_map.keys())
    ranked = sorted(all_users, key=lambda uid: total_map.get(uid, 0.0), reverse=True)

    for rank, uid in enumerate(ranked, 1):
        stmt = pg_insert(FantasyStandings).values(
            league_id=league_id,
            user_id=uid,
            total_points=total_map.get(uid, 0.0),
            week_points=week_map.get(uid, 0.0),
            rank=rank,
            updated_at=now,
        ).on_conflict_do_update(
            constraint="uq_fantasy_standings_league_user",
            set_={
                "total_points": total_map.get(uid, 0.0),
                "week_points": week_map.get(uid, 0.0),
                "rank": rank,
                "updated_at": now,
            },
        )
        pred.execute(stmt)
    pred.commit()


def get_round_state(league_id: int, viewer_user_id: int | None = None) -> dict:
    """
    Return the current trade-round state for the league page:
      {
        "round": {...} | None,
        "turns": [...],
        "current_turn": {...} | None,
        "is_my_turn": bool,
        "can_initiate": bool (caller is creator + no active round + active league),
      }
    """
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None:
        return {"round": None, "turns": [], "current_turn": None,
                "is_my_turn": False, "can_initiate": False}

    rnd = _active_round(league_id, pred)
    is_creator = viewer_user_id is not None and league.created_by == viewer_user_id

    if rnd is None:
        return {
            "round": None,
            "turns": [],
            "current_turn": None,
            "is_my_turn": False,
            "can_initiate": bool(is_creator and league.status == "active"),
        }

    turns = pred.execute(
        select(FantasyTradeTurn)
        .where(FantasyTradeTurn.round_id == rnd.id)
        .order_by(FantasyTradeTurn.pass_number.asc(), FantasyTradeTurn.turn_order.asc())
    ).scalars().all()
    current = _current_turn(rnd.id, pred)

    return {
        "round": rnd.to_dict(),
        "turns": [t.to_dict() for t in turns],
        "current_turn": current.to_dict() if current else None,
        "is_my_turn": bool(current and viewer_user_id and current.user_id == viewer_user_id),
        "can_initiate": False,  # already one in progress
    }


def _notify_turn(user_id: int, league_id: int, deadline, pred) -> None:
    """Notify a manager it's their turn to trade (mirrors draft notifications)."""
    try:
        from app.services.notify_service import notify_user, DRAFT_NOTIFY_DELAY_SECONDS
        deadline_str = deadline.astimezone().strftime("%b %d %I:%M %p %Z") if deadline else "soon"
        league_name = ""
        try:
            lg = pred.get(FantasyLeague, league_id)
            if lg:
                league_name = f" · {lg.name}"
        except Exception:
            pass
        notify_user(
            db=pred,
            user_id=user_id,
            title=f"🔁 Your Trade Turn!{league_name}",
            body=f"You're on the clock — make a trade or skip. Deadline {deadline_str}.",
            url=f"/fantasy/{league_id}?tab=trade",
            notif_type="fantasy_trade",
            delay_seconds=DRAFT_NOTIFY_DELAY_SECONDS,
        )
        pred.commit()
    except Exception as e:
        logger.warning("[trade] could not notify user=%d: %s", user_id, e)


def _hb_player_name(hb_human_id: int) -> str:
    """Best-effort 'First Last' for a HB human id (for notifications)."""
    try:
        from app.db import HBSession
        from sqlalchemy import text as sa_text
        row = HBSession().execute(
            sa_text("SELECT first_name, last_name FROM humans WHERE id = :hid"),
            {"hid": hb_human_id},
        ).fetchone()
        if row:
            return f"{row.first_name or ''} {row.last_name or ''}".strip() or f"#{hb_human_id}"
    except Exception:
        pass
    return f"#{hb_human_id}"


def _notify_auto_trade(user_id: int, league_id: int, release_hb_human_id: int,
                       acquire_hb_human_id: int, pred) -> None:
    """
    Notify a manager that we auto-traded for them after their turn expired
    (mirrors the auto-draft notification: fires immediately, delay=0).
    """
    try:
        from app.services.notify_service import notify_user
        league_name = ""
        try:
            lg = pred.get(FantasyLeague, league_id)
            if lg:
                league_name = f" · {lg.name}"
        except Exception:
            pass
        dropped = _hb_player_name(release_hb_human_id)
        added = _hb_player_name(acquire_hb_human_id)
        notify_user(
            db=pred,
            user_id=user_id,
            title=f"🔁 Auto-traded for you!{league_name}",
            body=f"Your turn expired — dropped {dropped} (0 pts) for {added}.",
            url=f"/fantasy/{league_id}?tab=trade",
            notif_type="fantasy_trade",
            delay_seconds=0,  # immediate — they missed their turn
        )
        pred.commit()
    except Exception as e:
        logger.warning("[trade] could not notify auto-trade for user=%d: %s", user_id, e)

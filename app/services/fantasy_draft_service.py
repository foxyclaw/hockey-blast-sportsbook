"""
fantasy_draft_service — manages the snake async draft.

Snake draft order example (3 managers):
  Round 1: M1, M2, M3
  Round 2: M3, M2, M1
  Round 3: M1, M2, M3
  ...

Missed turn: manager is skipped, gets compensatory_picks += 1.
Auto-pick: best available player by ppg from pool.
"""

import logging
from datetime import datetime, timezone, timedelta

# Draft quiet hours: picks do not expire before 10 AM PT (no one gets auto-skipped overnight)
_QUIET_START_HOUR = 0    # midnight PT
_QUIET_END_HOUR   = 10   # 10 AM PT
from zoneinfo import ZoneInfo as _ZoneInfo
_PT = _ZoneInfo("America/Los_Angeles")  # handles PDT/PST automatically


def _compute_pick_hours(league) -> float:
    """
    Compute the per-pick time window in hours.
    If draft_closes_at is set, distribute remaining window across remaining picks.
    Otherwise fall back to league.draft_pick_hours.
    """
    from sqlalchemy import select
    from app.db import PredSession
    from app.models.fantasy_draft_queue import FantasyDraftQueue

    if league.draft_closes_at:
        pred = PredSession()
        now_utc = datetime.now(timezone.utc)
        remaining_picks = pred.execute(
            select(FantasyDraftQueue).where(
                FantasyDraftQueue.league_id == league.id,
                FantasyDraftQueue.hb_human_id.is_(None),
                FantasyDraftQueue.is_skipped == False,  # noqa: E712
            )
        ).scalars().all()
        remaining = len(remaining_picks)
        if remaining > 0:
            window_end = league.draft_closes_at
            window_hours = (window_end - now_utc).total_seconds() / 3600
            if window_hours > 0:
                return max(1.0 / 60, window_hours / remaining)  # min 1 minute
            else:
                # Window already passed — give each remaining pick 5 minutes so
                # auto-pick cascades quickly instead of defaulting to 24h.
                return 5.0 / 60  # 5 minutes
    return float(league.draft_pick_hours)


def _deadline_respecting_quiet_hours(pick_hours: float) -> datetime:
    """
    Return now + pick_hours, but push the deadline past 10 AM PT if it
    would land during quiet hours (midnight–10 AM).

    Example: pick starts at 9 PM Friday, 24h deadline = 9 PM Saturday — fine.
    Example: pick starts at 2 AM Friday, 24h deadline = 2 AM Saturday —
             pushed to 10 AM Saturday so the manager isn't skipped overnight.
    """
    now_utc = datetime.now(timezone.utc)
    raw_deadline = now_utc + timedelta(hours=pick_hours)
    deadline_pt = raw_deadline.astimezone(_PT)

    if _QUIET_START_HOUR <= deadline_pt.hour < _QUIET_END_HOUR:
        # Deadline would land in quiet hours — restart the clock from 10 AM PT
        # i.e. 10 AM is when the pick window STARTS, so deadline = 10 AM + pick_hours
        wakeup = deadline_pt.replace(hour=_QUIET_END_HOUR, minute=0, second=0, microsecond=0)
        wakeup_with_window = wakeup + timedelta(hours=pick_hours)
        return wakeup_with_window.astimezone(timezone.utc)

    return raw_deadline

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import PredSession
from app.models.fantasy_league import FantasyLeague
from app.models.fantasy_manager import FantasyManager
from app.models.fantasy_roster import FantasyRoster
from app.models.fantasy_draft_queue import FantasyDraftQueue
from app.models.pred_notification import PredNotification

logger = logging.getLogger(__name__)


def build_draft_queue(league_id: int) -> None:
    """
    Generate the full snake draft order and insert into fantasy_draft_queue.
    Called when a league transitions from FORMING → DRAFT_OPEN.
    """
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None:
        raise ValueError(f"League {league_id} not found")

    # Get managers in draft order
    managers_stmt = (
        select(FantasyManager)
        .where(FantasyManager.league_id == league_id)
        .order_by(FantasyManager.draft_position.asc(), FantasyManager.joined_at.asc())
    )
    managers = pred.execute(managers_stmt).scalars().all()
    if not managers:
        raise ValueError("No managers in league")

    n = len(managers)
    total_rounds = league.roster_skaters + league.roster_goalies
    total_picks = n * total_rounds

    # Compute pick_hours dynamically from the draft window so the draft
    # always fits within draft_opens_at → draft_closes_at.
    # Fall back to league.draft_pick_hours if the window isn't set.
    if league.draft_closes_at and total_picks > 0:
        now_utc = datetime.now(timezone.utc)
        window_start = max(league.draft_opens_at or now_utc, now_utc)
        window_hours = (league.draft_closes_at - window_start).total_seconds() / 3600
        pick_hours = max(1.0, window_hours / total_picks)
        logger.info(
            "[draft] league=%d managers=%d picks=%d window=%.1fh → %.2fh/pick",
            league_id, n, total_picks, window_hours, pick_hours,
        )
    else:
        pick_hours = league.draft_pick_hours

    overall = 1
    entries = []
    # Round 1 = goalie picks; remaining rounds = skater picks
    for rnd in range(1, total_rounds + 1):
        is_goalie_round = (rnd == 1)
        # Snake: odd rounds forward, even rounds reverse
        if rnd % 2 == 1:
            order = list(range(n))
        else:
            order = list(range(n - 1, -1, -1))

        for pos_in_round, mgr_idx in enumerate(order, 1):
            mgr = managers[mgr_idx]
            entries.append({
                "league_id": league_id,
                "round": rnd,
                "pick_in_round": pos_in_round,
                "overall_pick": overall,
                "user_id": mgr.user_id,
                "hb_human_id": None,
                "is_skipped": False,
                "is_goalie_pick": is_goalie_round,
                "deadline": None,
                "picked_at": None,
            })
            overall += 1

    # Bulk insert
    pred.execute(
        pg_insert(FantasyDraftQueue).values(entries).on_conflict_do_nothing()
    )
    pred.commit()

    # Set deadline on first pick
    _set_next_deadline(league_id, pred, pick_hours)


def _set_next_deadline(league_id: int, pred, pick_hours: int) -> None:
    """Set deadline on the first unpicked, non-skipped slot."""
    stmt = (
        select(FantasyDraftQueue)
        .where(
            FantasyDraftQueue.league_id == league_id,
            FantasyDraftQueue.hb_human_id.is_(None),
            FantasyDraftQueue.is_skipped == False,  # noqa: E712
        )
        .order_by(FantasyDraftQueue.overall_pick.asc())
        .limit(1)
    )
    slot = pred.execute(stmt).scalar_one_or_none()
    if slot:
        slot.deadline = _deadline_respecting_quiet_hours(pick_hours)
        pred.commit()
        _notify_manager(slot.user_id, slot.league_id, slot.overall_pick, slot.deadline, pred)
    else:
        # No more unpicked slots — draft is complete, mark league active
        league = pred.get(FantasyLeague, league_id)
        if league and league.status == "drafting":
            league.status = "active"
            pred.commit()


def advance_draft(league_id: int) -> None:
    """
    Check if the current pick's deadline has passed. If so:
    - Skip the manager (mark is_skipped=True, compensatory_picks += 1)
    - Auto-pick best available player for them
    - Set deadline on next pick
    """
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None or league.status not in ("draft_open", "drafting"):
        return

    now = datetime.now(timezone.utc)

    # Find current pick
    stmt = (
        select(FantasyDraftQueue)
        .where(
            FantasyDraftQueue.league_id == league_id,
            FantasyDraftQueue.hb_human_id.is_(None),
            FantasyDraftQueue.is_skipped == False,  # noqa: E712
        )
        .order_by(FantasyDraftQueue.overall_pick.asc())
        .limit(1)
    )
    current = pred.execute(stmt).scalar_one_or_none()

    if current is None:
        # Draft complete
        league.status = "active"
        league.season_starts_at = now
        pred.commit()
        return

    if current.deadline is None or current.deadline > now:
        return  # Not yet expired

    # Timeout — auto-pick best available
    best = _best_available(league_id, current.user_id, pred, league)
    if best is not None:
        _record_pick(league_id, current, best["hb_human_id"], best["is_goalie"], pred, now)

        # Award compensatory pick
        mgr_stmt = select(FantasyManager).where(
            FantasyManager.league_id == league_id,
            FantasyManager.user_id == current.user_id,
        )
        mgr = pred.execute(mgr_stmt).scalar_one_or_none()
        if mgr:
            mgr.compensatory_picks += 1
    else:
        current.is_skipped = True
        pred.commit()

    _set_next_deadline(league_id, pred, _compute_pick_hours(league))


def make_pick(league_id: int, user_id: int, hb_human_id: int) -> dict:
    """
    Validate and record a draft pick.
    Returns the updated draft slot dict.
    Raises ValueError on validation failure.
    """
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)

    if league is None:
        raise ValueError("League not found")
    if league.status not in ("draft_open", "drafting"):
        raise ValueError(f"Draft is not open (status={league.status})")

    # Find current pick slot for this user
    stmt = (
        select(FantasyDraftQueue)
        .where(
            FantasyDraftQueue.league_id == league_id,
            FantasyDraftQueue.hb_human_id.is_(None),
            FantasyDraftQueue.is_skipped == False,  # noqa: E712
        )
        .order_by(FantasyDraftQueue.overall_pick.asc())
        .limit(1)
    )
    current = pred.execute(stmt).scalar_one_or_none()

    if current is None:
        raise ValueError("Draft is complete")

    if current.user_id != user_id:
        raise ValueError("It is not your turn to pick")

    # Check player not already drafted
    existing_stmt = select(FantasyRoster).where(
        FantasyRoster.league_id == league_id,
        FantasyRoster.hb_human_id == hb_human_id,
    )
    if pred.execute(existing_stmt).scalar_one_or_none() is not None:
        raise ValueError("Player already drafted in this league")

    # Determine if goalie
    pool = _get_pool(league_id)
    player_info = next(
        (p for p in pool["skaters"] + pool["goalies"] if p["hb_human_id"] == hb_human_id),
        None,
    )
    if player_info is None:
        raise ValueError("Player not in eligible pool for this league")

    # Enforce pick type — round 1 is goalie-only, all others are skater-only
    if current.is_goalie_pick and not player_info["is_goalie"]:
        raise ValueError("Round 1 is goalie picks only — please select a goalie")
    if not current.is_goalie_pick and player_info["is_goalie"]:
        raise ValueError("Goalies can only be picked in Round 1")

    now = datetime.now(timezone.utc)
    _record_pick(league_id, current, hb_human_id, player_info["is_goalie"], pred, now)

    # Clear this user's draft notifications now that they've picked
    _clear_stale_draft_notifications(user_id, league_id, pred)

    # Transition league status
    if league.status == "draft_open":
        league.status = "drafting"
        league.draft_started_at = now
        pred.commit()

    _set_next_deadline(league_id, pred, _compute_pick_hours(league))

    return current.to_dict()


def _record_pick(league_id, slot, hb_human_id, is_goalie, pred, now) -> None:
    slot.hb_human_id = hb_human_id
    slot.picked_at = now

    entry = FantasyRoster(
        league_id=league_id,
        user_id=slot.user_id,
        hb_human_id=hb_human_id,
        is_goalie=is_goalie,
        round_picked=slot.round,
        pick_number=slot.overall_pick,
        drafted_at=now,
    )
    pred.add(entry)
    pred.commit()


def _best_available(league_id: int, user_id: int, pred, league) -> dict | None:
    """Return the best available (undrafted) player by ppg."""
    pool = _get_pool(league_id)
    drafted_stmt = select(FantasyRoster.hb_human_id).where(
        FantasyRoster.league_id == league_id
    )
    drafted_ids = set(pred.execute(drafted_stmt).scalars().all())

    # Check what the manager still needs (skaters vs goalies)
    manager_roster_stmt = select(FantasyRoster).where(
        FantasyRoster.league_id == league_id,
        FantasyRoster.user_id == user_id,
    )
    manager_roster = pred.execute(manager_roster_stmt).scalars().all()
    goalie_count = sum(1 for r in manager_roster if r.is_goalie)
    skater_count = sum(1 for r in manager_roster if not r.is_goalie)

    needs_goalie = goalie_count < league.roster_goalies
    needs_skater = skater_count < league.roster_skaters

    candidates = []
    if needs_goalie:
        candidates += [p for p in pool["goalies"] if p["hb_human_id"] not in drafted_ids]
    if needs_skater:
        candidates += [p for p in pool["skaters"] if p["hb_human_id"] not in drafted_ids]

    if not candidates:
        return None

    # Use fantasy_points (total, same sort as UI pool list)
    return max(candidates, key=lambda p: p.get("fantasy_points", 0))


def _get_pool(league_id: int) -> dict:
    """Get the level pool for this league."""
    from app.services.fantasy_pool_service import get_player_pool
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    return get_player_pool(league.level_id, league_id=league.hb_league_id, season_id=league.hb_season_id)


def _clear_stale_draft_notifications(user_id: int, league_id: int, pred) -> None:
    """Delete ALL previous draft pick notifications for this user."""
    from app.models.pred_notification import PredNotification
    try:
        stale = pred.query(PredNotification).filter(
            PredNotification.user_id == user_id,
            PredNotification.type == "fantasy_draft",
        ).all()
        for n in stale:
            pred.delete(n)
    except Exception:
        pass


def _notify_manager(user_id: int, league_id: int, pick_number: int, deadline: datetime, pred) -> None:
    """Create a push notification for a manager's draft turn."""
    try:
        # Clear previous unread draft notifications for this league to avoid pileup
        _clear_stale_draft_notifications(user_id, league_id, pred)
        notif = PredNotification(
            user_id=user_id,
            type="fantasy_draft",
            title="🏒 Your Pick!",
            body=f"Pick #{pick_number} — draft until {deadline.astimezone().strftime('%b %d %I:%M %p %Z')}.",
            link=f"/fantasy/{league_id}",
        )
        pred.add(notif)
        pred.commit()
    except Exception as e:
        logger.warning(f"Could not create draft notification: {e}")

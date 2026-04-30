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

    Rules:
    - If draft_closes_at is set: ALWAYS derive from the window, never use draft_pick_hours.
      * Window still open: remaining_window / remaining_picks (min 1 min)
      * Window already passed: 5 minutes per pick so auto-pick cascades fast
    - If draft_closes_at is NOT set: use draft_pick_hours (async-style league, e.g. 24h/pick)
    """
    from sqlalchemy import select
    from app.db import PredSession
    from app.models.fantasy_draft_queue import FantasyDraftQueue

    if league.draft_closes_at:
        pred = PredSession()
        now_utc = datetime.now(timezone.utc)
        remaining = pred.execute(
            select(FantasyDraftQueue).where(
                FantasyDraftQueue.league_id == league.id,
                FantasyDraftQueue.hb_human_id.is_(None),
                FantasyDraftQueue.is_skipped == False,  # noqa: E712
            ).with_only_columns(FantasyDraftQueue.id)
        ).scalars().all()
        count = len(remaining)
        if count > 0:
            window_hours = (league.draft_closes_at - now_utc).total_seconds() / 3600
            if window_hours > 0:
                return max(1.0 / 60, window_hours / count)  # min 1 minute
            else:
                return 5.0 / 60  # window passed — 5 min per pick to cascade fast
        return 1.0 / 60  # nothing left, 1 min

    # No draft_closes_at — true async league, use configured pick hours
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

    # Auto-adjust roster sizes from the actual pool / actual manager count
    # (e.g. 6 managers → 10-1-1; 10 managers → 6-0-0).
    if league.auto_adjust_rosters:
        from app.services.fantasy_pool_service import get_player_pool
        try:
            pool_info = get_player_pool(
                league.level_id,
                org_id=league.org_id,
                league_id=league.hb_league_id,
                season_id=league.draft_season_id or league.hb_season_id,
                min_games=league.min_games_played or 1,
            )
            total_skaters = len(pool_info.get("skaters", []))
            total_goalies = len(pool_info.get("goalies", []))
            total_refs = len(pool_info.get("refs", []))
            league.roster_skaters = max(1, min(10, total_skaters // n))
            league.roster_goalies = max(0, min(1, total_goalies // n))
            league.roster_refs = max(0, min(1, total_refs // n))
            pred.commit()
        except Exception as e:
            logger.warning("[draft] auto-roster sizing failed for league=%d: %s", league_id, e)

    total_rounds = league.roster_skaters + league.roster_goalies + league.roster_refs
    total_picks = n * total_rounds

    # Compute pick_hours dynamically from the draft window so the draft
    # always fits within draft_opens_at → draft_closes_at.
    # Fall back to league.draft_pick_hours if the window isn't set.
    if league.draft_closes_at and total_picks > 0:
        now_utc = datetime.now(timezone.utc)
        window_start = max(league.draft_opens_at or now_utc, now_utc)
        window_hours = (league.draft_closes_at - window_start).total_seconds() / 3600
        pick_hours = max(1.0 / 60, window_hours / total_picks)  # min 1 minute, no 1h floor
        logger.info(
            "[draft] league=%d managers=%d picks=%d window=%.1fh → %.2fh/pick",
            league_id, n, total_picks, window_hours, pick_hours,
        )
    else:
        pick_hours = league.draft_pick_hours

    overall = 1
    entries = []
    # Round 1 = goalie picks; last round = ref picks; remaining = skater picks
    goalie_round = 1
    ref_round = total_rounds if league.roster_refs > 0 else None
    for rnd in range(1, total_rounds + 1):
        is_goalie_round = (rnd == goalie_round)
        is_ref_round = (rnd == ref_round)
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
                "is_ref_pick": is_ref_round or False,
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


def _set_next_deadline(league_id: int, pred, pick_hours: int, prev_was_auto: bool = False) -> None:
    """Set deadline on the first unpicked, non-skipped slot.

    If the next manager has a non-empty priority queue with an available player,
    auto-pick immediately on their behalf instead of waiting for them.
    Loops (not recurses) to chain auto-picks safely across many managers.
    """
    MAX_AUTO_PICKS = 500  # hard safety cap — full draft is n_managers * total_rounds

    for _ in range(MAX_AUTO_PICKS):
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
        if not slot:
            # No more unpicked slots — draft is complete, mark league active
            league = pred.get(FantasyLeague, league_id)
            if league and league.status == "drafting":
                league.status = "active"
                if not league.draft_season_id:
                    league.draft_season_id = league.hb_season_id
                pred.commit()
            return

        league = pred.get(FantasyLeague, league_id)

        # Check if this manager has a queued player ready — if so, auto-pick immediately
        best = _best_available_from_queue_only(league_id, slot.user_id, pred, league, current_slot=slot)
        if best is not None:
            logger.info(
                "[draft] league=%d pick=%d user=%d — queue hit, auto-picking hb_human_id=%d",
                league_id, slot.overall_pick, slot.user_id, best["hb_human_id"],
            )
            now = datetime.now(timezone.utc)
            slot.deadline = now
            pred.commit()
            _record_pick(league_id, slot, best["hb_human_id"],
                is_goalie=slot.is_goalie_pick and best.get("is_goalie", False),
                pred=pred, now=now,
                is_ref=slot.is_ref_pick and best.get("is_ref", False))
            _player_name = f"{best.get('first_name', '')} {best.get('last_name', '')}".strip() or None
            _notify_manager(slot.user_id, league_id, slot.overall_pick, now, pred,
                            auto_picked_from_queue=True, player_name=_player_name)
            if league and league.status == "draft_open":
                league.status = "drafting"
                league.draft_started_at = now
                pred.commit()
            # Loop to check the next pick
            continue

        # No queue hit — set deadline and wait for manual pick
        slot.deadline = _deadline_respecting_quiet_hours(pick_hours)
        pred.commit()
        _notify_manager(slot.user_id, slot.league_id, slot.overall_pick, slot.deadline, pred)
        return


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

    # Find current pick — use FOR UPDATE SKIP LOCKED to prevent duplicate auto-picks
    # if the scheduler fires concurrently
    stmt = (
        select(FantasyDraftQueue)
        .where(
            FantasyDraftQueue.league_id == league_id,
            FantasyDraftQueue.hb_human_id.is_(None),
            FantasyDraftQueue.is_skipped == False,  # noqa: E712
        )
        .order_by(FantasyDraftQueue.overall_pick.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    current = pred.execute(stmt).scalar_one_or_none()

    if current is None:
        # Draft complete
        league.status = "active"
        league.season_starts_at = now
        if not league.draft_season_id:
            league.draft_season_id = league.hb_season_id
        pred.commit()
        return

    if current.deadline is None or current.deadline > now:
        return  # Not yet expired

    # Timeout — auto-pick best available (respects manager's priority queue)
    best = _best_available(league_id, current.user_id, pred, league, current_slot=current)
    if best is not None:
        _record_pick(league_id, current, best["hb_human_id"],
            is_goalie=current.is_goalie_pick and best.get("is_goalie", False),
            pred=pred, now=now,
            is_ref=current.is_ref_pick and best.get("is_ref", False))

        # Notify the manager that we picked for them (immediate SMS)
        _timeout_player_name = f"{best.get('first_name', '')} {best.get('last_name', '')}".strip() or None
        _notify_manager(
            current.user_id, league_id, current.overall_pick,
            current.deadline, pred, auto_picked=True, player_name=_timeout_player_name
        )

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
    # Search the correct pool based on pick type to avoid cross-contamination
    if current.is_goalie_pick:
        search_pool = pool["goalies"]
    elif current.is_ref_pick:
        search_pool = pool.get("refs", [])
    else:
        search_pool = pool["skaters"]
    player_info = next((p for p in search_pool if p["hb_human_id"] == hb_human_id), None)
    # Fallback: search all pools (handles edge cases like a player in multiple pools)
    if player_info is None:
        player_info = next(
            (p for p in pool["goalies"] + pool.get("refs", []) + pool["skaters"] if p["hb_human_id"] == hb_human_id),
            None,
        )
    if player_info is None:
        raise ValueError("Player not in eligible pool for this league")

    # Enforce pick type using role flags
    if current.is_goalie_pick and not player_info.get("is_goalie"):
        raise ValueError("This is a goalie pick — please select a goalie")
    if current.is_ref_pick and not player_info.get("is_ref"):
        raise ValueError("This is a referee pick — please select a referee")
    if not current.is_goalie_pick and not current.is_ref_pick:
        if player_info.get("is_goalie") and not player_info.get("is_skater"):
            raise ValueError("Goalies can only be picked in the goalie round")
        if player_info.get("is_ref") and not player_info.get("is_skater"):
            raise ValueError("Referees can only be picked in the referee round")

    now = datetime.now(timezone.utc)
    _record_pick(league_id, current, hb_human_id,
        is_goalie=current.is_goalie_pick and player_info.get("is_goalie", False),
        pred=pred, now=now,
        is_ref=current.is_ref_pick and player_info.get("is_ref", False))

    # Clear this user's draft notifications now that they've picked
    _clear_stale_draft_notifications(user_id, league_id, pred)

    # Transition league status
    if league.status == "draft_open":
        league.status = "drafting"
        league.draft_started_at = now
        pred.commit()

    _set_next_deadline(league_id, pred, _compute_pick_hours(league))

    return current.to_dict()


def _record_pick(league_id, slot, hb_human_id, is_goalie, pred, now, is_ref=False) -> None:
    slot.hb_human_id = hb_human_id
    slot.picked_at = now

    entry = FantasyRoster(
        league_id=league_id,
        user_id=slot.user_id,
        hb_human_id=hb_human_id,
        is_goalie=is_goalie,
        is_ref=is_ref,
        round_picked=slot.round,
        pick_number=slot.overall_pick,
        drafted_at=now,
    )
    pred.add(entry)
    pred.commit()


def _best_available_from_queue_only(league_id: int, user_id: int, pred, league, current_slot=None) -> dict | None:
    """Return the first available player from the manager's priority queue only.
    Returns None if queue is empty or no queued player is available for this pick type.
    Does NOT fall back to best-by-points — that's for timeout auto-picks only.
    """
    from app.models.fantasy_manager_queue import FantasyManagerQueue
    queue_stmt = (
        select(FantasyManagerQueue)
        .where(
            FantasyManagerQueue.league_id == league_id,
            FantasyManagerQueue.user_id == user_id,
        )
        .order_by(FantasyManagerQueue.position.asc())
    )
    queue_items = pred.execute(queue_stmt).scalars().all()
    if not queue_items:
        return None  # no queue — wait for manual pick

    pool = _get_pool(league_id)
    drafted_stmt = select(FantasyRoster.hb_human_id).where(FantasyRoster.league_id == league_id)
    drafted_ids = set(pred.execute(drafted_stmt).scalars().all())

    is_goalie_pick = current_slot.is_goalie_pick if current_slot else False
    is_ref_pick = current_slot.is_ref_pick if current_slot else False

    if is_goalie_pick:
        eligible = {p["hb_human_id"]: p for p in pool["goalies"] if p["hb_human_id"] not in drafted_ids}
    elif is_ref_pick:
        eligible = {p["hb_human_id"]: p for p in pool.get("refs", []) if p["hb_human_id"] not in drafted_ids}
    else:
        all_skaters = [p for p in pool["skaters"] if p["hb_human_id"] not in drafted_ids]
        eligible = {p["hb_human_id"]: p for p in all_skaters}

    for item in queue_items:
        if item.hb_human_id in eligible:
            return eligible[item.hb_human_id]

    return None  # queue exists but all queued players are already drafted or wrong type


def _best_available(league_id: int, user_id: int, pred, league, current_slot=None) -> dict | None:
    """Return the best available (undrafted) player.

    Priority order:
    1. First available player from the manager's priority queue (respecting goalie enforcement)
    2. Fallback: best by fantasy_points from eligible pool
    """
    pool = _get_pool(league_id)
    drafted_stmt = select(FantasyRoster.hb_human_id).where(
        FantasyRoster.league_id == league_id
    )
    drafted_ids = set(pred.execute(drafted_stmt).scalars().all())

    # Check what the manager still needs
    manager_roster_stmt = select(FantasyRoster).where(
        FantasyRoster.league_id == league_id,
        FantasyRoster.user_id == user_id,
    )
    manager_roster = pred.execute(manager_roster_stmt).scalars().all()
    goalie_count = sum(1 for r in manager_roster if r.is_goalie)
    skater_count = sum(1 for r in manager_roster if not r.is_goalie and not r.is_ref)
    ref_count = sum(1 for r in manager_roster if r.is_ref)

    picks_remaining = _picks_remaining_for_manager(league_id, user_id, pred)
    goalies_still_needed = max(0, league.roster_goalies - goalie_count)
    refs_still_needed = max(0, league.roster_refs - ref_count)

    is_goalie_pick = current_slot.is_goalie_pick if current_slot else False
    is_ref_pick = current_slot.is_ref_pick if current_slot else False

    # Build the full available pool for this pick type
    all_pool = pool["goalies"] + pool.get("refs", []) + pool["skaters"]
    if is_goalie_pick:
        eligible = [p for p in pool["goalies"] if p["hb_human_id"] not in drafted_ids]
    elif is_ref_pick:
        eligible = [p for p in pool.get("refs", []) if p["hb_human_id"] not in drafted_ids]
    else:
        eligible = [p for p in all_pool if p["hb_human_id"] not in drafted_ids
                    and not p.get("is_ref")]
        # If this manager must pick a goalie now (last picks remaining = goalies needed),
        # force goalie regardless of queue
        force_goalie = (picks_remaining > 0 and picks_remaining <= goalies_still_needed)
        if force_goalie:
            eligible = [p for p in pool["goalies"] if p["hb_human_id"] not in drafted_ids]

    if not eligible:
        return None

    # Try manager's priority queue first
    from app.models.fantasy_manager_queue import FantasyManagerQueue
    queue_stmt = (
        select(FantasyManagerQueue)
        .where(
            FantasyManagerQueue.league_id == league_id,
            FantasyManagerQueue.user_id == user_id,
        )
        .order_by(FantasyManagerQueue.position.asc())
    )
    queue_items = pred.execute(queue_stmt).scalars().all()
    eligible_ids = {p["hb_human_id"] for p in eligible}

    for item in queue_items:
        if item.hb_human_id in eligible_ids:
            return next(p for p in eligible if p["hb_human_id"] == item.hb_human_id)

    # Fallback: best by fantasy_points
    return max(eligible, key=lambda p: p.get("fantasy_points", 0))


def _picks_remaining_for_manager(league_id: int, user_id: int, pred) -> int:
    """Count unpicked, non-skipped slots remaining for this manager."""
    stmt = select(FantasyDraftQueue).where(
        FantasyDraftQueue.league_id == league_id,
        FantasyDraftQueue.user_id == user_id,
        FantasyDraftQueue.hb_human_id.is_(None),
        FantasyDraftQueue.is_skipped == False,  # noqa: E712
    )
    return len(pred.execute(stmt).scalars().all())


def _get_pool(league_id: int) -> dict:
    """Get the level pool for this league (always uses draft_season_id, not play season)."""
    from app.services.fantasy_pool_service import get_player_pool
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    return get_player_pool(
        league.level_id,
        org_id=league.org_id,
        league_id=league.hb_league_id,
        season_id=league.draft_season_id or league.hb_season_id,
        min_games=league.min_games_played or 1,
    )


def _clear_stale_draft_notifications(user_id: int, league_id: int, pred) -> None:
    """Mark stale 'your turn' prompts as read — keep them in history, don't delete."""
    from app.models.pred_notification import PredNotification
    try:
        stale = pred.query(PredNotification).filter(
            PredNotification.user_id == user_id,
            PredNotification.type == "fantasy_draft",
            PredNotification.title.like("%Your Pick%"),
            PredNotification.is_read == False,
        ).all()
        for n in stale:
            n.is_read = True
    except Exception:
        pass


def _notify_manager(user_id: int, league_id: int, pick_number: int, deadline: datetime, pred,
                    auto_picked: bool = False, auto_picked_from_queue: bool = False,
                    player_name: str = None) -> None:
    """
    Notify a manager it's their turn to pick.
    - Normal turn: SMS fires after 2 min if they haven't opened the app
    - Auto-picked on timeout: SMS fires immediately (they missed their turn)
    - Auto-picked from queue: SMS fires immediately (picked from their priority queue)
    """
    try:
        _clear_stale_draft_notifications(user_id, league_id, pred)
        from app.services.notify_service import notify_user, DRAFT_NOTIFY_DELAY_SECONDS
        deadline_str = deadline.astimezone().strftime("%b %d %I:%M %p %Z") if deadline else "soon"

        # Get league name for context
        league_name = ""
        try:
            league_obj = pred.get(FantasyLeague, league_id)
            if league_obj:
                league_name = f" · {league_obj.name}"
        except Exception:
            pass

        player_str = f" — {player_name}" if player_name else ""

        if auto_picked_from_queue:
            title = f"🏒 Picked from your queue!{league_name}"
            body = f"Pick #{pick_number} from your queue{player_str}."
            delay = 0  # immediate
        elif auto_picked:
            title = f"🏒 Auto-picked for you!{league_name}"
            body = f"Pick #{pick_number} — top available player{player_str}."
            delay = 0  # immediate — they need to know
        else:
            title = f"🏒 Your Pick!{league_name}"
            body = f"Pick #{pick_number} — deadline {deadline_str}."
            delay = DRAFT_NOTIFY_DELAY_SECONDS  # 2 min

        notify_user(
            db=pred,
            user_id=user_id,
            title=title,
            body=body,
            url=f"/fantasy/{league_id}?tab=draft",
            notif_type="fantasy_draft",
            delay_seconds=delay,
        )
        pred.commit()
    except Exception as e:
        logger.warning(f"Could not create draft notification: {e}")

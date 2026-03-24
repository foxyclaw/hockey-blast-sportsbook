"""
Fantasy blueprint.

GET  /api/fantasy/levels               — list eligible levels with pool sizes
POST /api/fantasy/leagues              — create a league (require_auth)
GET  /api/fantasy/leagues              — list all leagues (optional_auth)
GET  /api/fantasy/leagues/<id>         — league detail + managers + status
POST /api/fantasy/leagues/<id>/join    — join a league (require_auth)
GET  /api/fantasy/leagues/<id>/pool    — available players (not yet drafted)
POST /api/fantasy/leagues/<id>/draft   — make a pick (require_auth)
GET  /api/fantasy/leagues/<id>/draft/queue — current draft state
GET  /api/fantasy/leagues/<id>/roster/<user_id> — a manager's roster
GET  /api/fantasy/leagues/<id>/standings   — league standings
POST /api/fantasy/leagues/<id>/open-draft  — open draft (creator only, require_auth)
POST /api/fantasy/leagues/<id>/start   — start season (creator only, require_auth)
"""

import random
import string
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select, func, or_

from app.auth.jwt_validator import require_auth, optional_auth
from app.db import HBSession, PredSession
from app.models.fantasy_league import FantasyLeague
from app.models.fantasy_manager import FantasyManager
from app.models.fantasy_roster import FantasyRoster
from app.models.fantasy_draft_queue import FantasyDraftQueue
from app.models.fantasy_standings import FantasyStandings
from app.models.pred_user import PredUser
from app.utils.response import error_response

fantasy_bp = Blueprint("fantasy", __name__)


# ── Levels ────────────────────────────────────────────────────────────────────

@fantasy_bp.route("/levels", methods=["GET"])
@optional_auth
def list_levels():
    """GET /api/fantasy/levels — list levels that have a fantasy league for the current season."""
    from hockey_blast_common_lib.models import Level
    from hockey_blast_common_lib.stats_models import LevelStatsSkater
    from app.models.fantasy_league import FantasyLeague
    from app.db import PredSession

    hb = HBSession()
    pred = PredSession()
    org_id = request.args.get("org_id", 1, type=int)
    season_label = request.args.get("season_label", "Spring 2026")

    # Level IDs that already have a fantasy league for this org+season
    existing_level_ids = {
        row.level_id for row in pred.execute(
            select(FantasyLeague.level_id)
            .where(
                FantasyLeague.org_id == org_id,
                FantasyLeague.season_label == season_label,
                FantasyLeague.status.notin_(["completed"]),
            )
        ).all()
    }

    if not existing_level_ids:
        return jsonify({"levels": []})

    # Get those levels with skater counts
    stmt = (
        select(Level, func.count(LevelStatsSkater.human_id).label("skater_count"))
        .join(LevelStatsSkater, LevelStatsSkater.level_id == Level.id, isouter=True)
        .where(Level.id.in_(existing_level_ids))
        .group_by(Level.id)
        .order_by(Level.skill_value.asc().nullslast())
    )

    rows = hb.execute(stmt).all()
    levels = []
    for level, skater_count in rows:
        usable = int(skater_count * 0.7)
        roster_skaters = 5
        for r in range(10, 4, -1):
            if usable // r >= 4:
                roster_skaters = r
                break
        max_managers = min(12, usable // roster_skaters) if roster_skaters > 0 else 4
        max_managers = max(0, max_managers)
        if max_managers < 4:
            continue  # skip levels with insufficient pool

        levels.append({
            "level_id": level.id,
            "level_name": level.short_name or level.level_name or str(level.id),
            "org_id": level.org_id,
            "skater_count": skater_count,
            "roster_skaters": roster_skaters,
            "max_managers": max_managers,
        })

    return jsonify({"levels": levels})


# ── Leagues ───────────────────────────────────────────────────────────────────

@fantasy_bp.route("/leagues", methods=["POST"])
@require_auth
def create_league():
    """POST /api/fantasy/leagues — create a new fantasy league."""
    data = request.get_json(force=True, silent=True) or {}
    user = g.pred_user

    level_id = data.get("level_id")
    name = (data.get("name") or "").strip()
    team_name = (data.get("team_name") or "").strip()

    if not level_id:
        return error_response("VALIDATION_ERROR", "level_id is required", 400)
    if not name:
        return error_response("VALIDATION_ERROR", "name is required", 400)
    if not team_name:
        return error_response("VALIDATION_ERROR", "team_name is required", 400)

    # Look up level info from HB
    from hockey_blast_common_lib.models import Level
    hb = HBSession()
    level = hb.execute(select(Level).where(Level.id == level_id)).scalar_one_or_none()
    if level is None:
        return error_response("NOT_FOUND", f"Level {level_id} not found", 404)

    level_name = level.short_name or level.level_name or str(level_id)

    # Compute roster sizing
    from app.services.fantasy_pool_service import get_player_pool
    try:
        pool_info = get_player_pool(level_id)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"Could not load player pool: {e}", 500)

    roster_skaters = pool_info["roster_skaters"]
    max_managers = pool_info["max_managers"]

    if max_managers < 4:
        return error_response("VALIDATION_ERROR", "Not enough players at this level to form a league (need 4+ managers worth of players)", 400)

    # Handle private league + join_code
    is_private = bool(data.get("is_private", False))
    join_code = None
    if is_private:
        join_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    pred = PredSession()
    try:
        # Parse optional datetime fields
        def _parse_dt(val):
            if not val:
                return None
            from datetime import timezone as _tz
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(val, fmt)
                    return dt.replace(tzinfo=_tz.utc)
                except ValueError:
                    continue
            return None

        league = FantasyLeague(
            name=name,
            level_id=level_id,
            level_name=level_name,
            org_id=level.org_id,
            season_label=data.get("season_label"),
            status="forming",
            max_managers=max_managers,
            roster_skaters=roster_skaters,
            roster_goalies=1,
            draft_pick_hours=data.get("draft_pick_hours", 24),
            created_by=user.id,
            is_private=is_private,
            join_code=join_code,
            season_starts_at=_parse_dt(data.get("season_starts_at")),
            draft_opens_at=_parse_dt(data.get("draft_opens_at")),
            draft_closes_at=_parse_dt(data.get("draft_closes_at")),
        )
        pred.add(league)
        pred.flush()

        mgr = FantasyManager(
            league_id=league.id,
            user_id=user.id,
            team_name=team_name,
        )
        pred.add(mgr)
        pred.commit()
        pred.refresh(league)

    except Exception as e:
        pred.rollback()
        return error_response("INTERNAL_ERROR", str(e), 500)

    return jsonify(league.to_dict()), 201


@fantasy_bp.route("/leagues", methods=["GET"])
@optional_auth
def list_leagues():
    """GET /api/fantasy/leagues — list all leagues."""
    pred = PredSession()
    status_filter = request.args.get("status")

    stmt = select(FantasyLeague).order_by(FantasyLeague.created_at.desc())
    if status_filter:
        stmt = stmt.where(FantasyLeague.status == status_filter)

    # Filter: only show public leagues OR leagues where user is a member
    if g.pred_user:
        member_league_ids = select(FantasyManager.league_id).where(FantasyManager.user_id == g.pred_user.id)
        stmt = stmt.where(
            or_(
                FantasyLeague.is_private == False,  # noqa: E712
                FantasyLeague.id.in_(member_league_ids),
            )
        )
    else:
        stmt = stmt.where(FantasyLeague.is_private == False)  # noqa: E712

    leagues = pred.execute(stmt).scalars().all()

    result = []
    for league in leagues:
        mgr_count = pred.execute(
            select(func.count()).select_from(FantasyManager).where(FantasyManager.league_id == league.id)
        ).scalar_one()
        d = league.to_dict()
        d["manager_count"] = mgr_count

        # Is current user a member? Is it their turn to draft?
        if g.pred_user:
            mgr = pred.execute(
                select(FantasyManager).where(
                    FantasyManager.league_id == league.id,
                    FantasyManager.user_id == g.pred_user.id,
                )
            ).scalar_one_or_none()
            d["is_member"] = mgr is not None

            # Check if it's the user's turn in the draft
            is_your_turn = False
            if mgr and league.status in ("drafting", "draft_open"):
                from app.models.fantasy_draft_queue import FantasyDraftQueue
                current_pick = pred.execute(
                    select(FantasyDraftQueue)
                    .where(
                        FantasyDraftQueue.league_id == league.id,
                        FantasyDraftQueue.hb_human_id.is_(None),
                        FantasyDraftQueue.is_skipped == False,  # noqa: E712
                    )
                    .order_by(FantasyDraftQueue.overall_pick.asc())
                    .limit(1)
                ).scalar_one_or_none()
                is_your_turn = current_pick is not None and current_pick.user_id == g.pred_user.id
            d["is_your_turn"] = is_your_turn
        else:
            d["is_member"] = False
            d["is_your_turn"] = False

        result.append(d)

    return jsonify({"leagues": result})


@fantasy_bp.route("/leagues/<int:league_id>", methods=["GET"])
@optional_auth
def get_league(league_id: int):
    """GET /api/fantasy/leagues/<id> — league detail with managers."""
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None:
        return error_response("NOT_FOUND", "League not found", 404)

    # Get managers with user info
    mgr_stmt = (
        select(FantasyManager, PredUser)
        .join(PredUser, FantasyManager.user_id == PredUser.id)
        .where(FantasyManager.league_id == league_id)
        .order_by(FantasyManager.draft_position.asc().nullslast(), FantasyManager.joined_at.asc())
    )
    mgr_rows = pred.execute(mgr_stmt).all()

    managers = []
    for mgr, user in mgr_rows:
        m = mgr.to_dict()
        m["display_name"] = user.display_name
        m["avatar_url"] = user.avatar_url
        managers.append(m)

    d = league.to_dict()
    d["managers"] = managers
    d["manager_count"] = len(managers)

    if g.pred_user:
        is_member = any(m["user_id"] == g.pred_user.id for m in managers)
        d["is_member"] = is_member
        d["is_creator"] = league.created_by == g.pred_user.id
    else:
        d["is_member"] = False
        d["is_creator"] = False

    return jsonify(d)


@fantasy_bp.route("/leagues/<int:league_id>/join", methods=["POST"])
@require_auth
def join_league(league_id: int):
    """POST /api/fantasy/leagues/<id>/join — join a league."""
    pred = PredSession()
    user = g.pred_user
    data = request.get_json(force=True, silent=True) or {}
    team_name = (data.get("team_name") or "").strip()

    if not team_name:
        return error_response("VALIDATION_ERROR", "team_name is required", 400)

    league = pred.get(FantasyLeague, league_id)
    if league is None:
        return error_response("NOT_FOUND", "League not found", 404)
    if league.status != "forming":
        return error_response("CONFLICT", "League is no longer accepting managers", 409)

    # Validate join_code for private leagues
    if league.is_private:
        submitted_code = (data.get("join_code") or "").strip().upper()
        if not submitted_code:
            return error_response("VALIDATION_ERROR", "join_code is required for private leagues", 400)
        if submitted_code != (league.join_code or "").upper():
            return error_response("FORBIDDEN", "Invalid join code", 403)

    # Check already joined
    existing = pred.execute(
        select(FantasyManager).where(
            FantasyManager.league_id == league_id,
            FantasyManager.user_id == user.id,
        )
    ).scalar_one_or_none()
    if existing:
        return error_response("CONFLICT", "You are already in this league", 409)

    # Check capacity
    mgr_count = pred.execute(
        select(func.count()).select_from(FantasyManager).where(FantasyManager.league_id == league_id)
    ).scalar_one()
    if mgr_count >= league.max_managers:
        return error_response("CONFLICT", "League is full", 409)

    try:
        mgr = FantasyManager(
            league_id=league_id,
            user_id=user.id,
            team_name=team_name,
        )
        pred.add(mgr)
        pred.commit()

        # Auto-open draft when league hits max_managers
        new_count = mgr_count + 1
        if new_count >= league.max_managers and league.status == "forming":
            import random as _random
            managers = pred.execute(
                select(FantasyManager).where(FantasyManager.league_id == league_id)
            ).scalars().all()
            positions = list(range(1, len(managers) + 1))
            _random.shuffle(positions)
            for m, pos in zip(managers, positions):
                m.draft_position = pos
            league.status = "draft_open"
            pred.commit()

            from app.services.fantasy_draft_service import build_draft_queue
            try:
                build_draft_queue(league_id)
            except Exception as e:
                pass  # draft queue build failure shouldn't block the join response

    except Exception as e:
        pred.rollback()
        return error_response("INTERNAL_ERROR", str(e), 500)

    return jsonify(mgr.to_dict()), 201


@fantasy_bp.route("/leagues/<int:league_id>/pool", methods=["GET"])
@optional_auth
def get_pool(league_id: int):
    """GET /api/fantasy/leagues/<id>/pool — available (undrafted) players."""
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None:
        return error_response("NOT_FOUND", "League not found", 404)

    from app.services.fantasy_pool_service import get_player_pool
    try:
        pool = get_player_pool(league.level_id, org_id=league.org_id, league_id=league.hb_league_id, season_id=league.hb_season_id)
    except Exception as e:
        return error_response("INTERNAL_ERROR", str(e), 500)

    # Query who drafted which players in this league
    roster_rows = pred.execute(
        select(FantasyRoster.hb_human_id, FantasyRoster.user_id)
        .where(FantasyRoster.league_id == league_id)
    ).all()

    # Build drafted map: hb_human_id -> user_id
    drafted_map = {row.hb_human_id: row.user_id for row in roster_rows}
    drafted_ids = set(drafted_map.keys())

    # Build manager team name map
    mgr_rows = pred.execute(
        select(FantasyManager.user_id, FantasyManager.team_name)
        .where(FantasyManager.league_id == league_id)
    ).all()
    mgr_team_map = {row.user_id: row.team_name for row in mgr_rows}

    def enrich_drafted(player):
        hid = player["hb_human_id"]
        if hid in drafted_map:
            uid = drafted_map[hid]
            player["drafted_by"] = {"user_id": uid, "team_name": mgr_team_map.get(uid)}
        else:
            player["drafted_by"] = None
        return player

    # Apply type filter
    type_filter = request.args.get("type", "").lower()

    all_skaters = [enrich_drafted(p) for p in pool["skaters"]]
    all_goalies = [enrich_drafted(p) for p in pool["goalies"]]

    # Sort: skaters by fantasy_ppg DESC, goalies by fantasy_points DESC
    all_skaters.sort(key=lambda p: p.get("fantasy_ppg", 0), reverse=True)
    all_goalies.sort(key=lambda p: p.get("fantasy_points", 0), reverse=True)

    if type_filter == "skaters":
        return jsonify({"skaters": all_skaters, "goalies": []})
    elif type_filter == "goalies":
        return jsonify({"skaters": [], "goalies": all_goalies})

    return jsonify({
        "skaters": all_skaters,
        "goalies": all_goalies,
    })


@fantasy_bp.route("/leagues/<int:league_id>/draft", methods=["POST"])
@require_auth
def make_pick(league_id: int):
    """POST /api/fantasy/leagues/<id>/draft — make a pick."""
    user = g.pred_user
    data = request.get_json(force=True, silent=True) or {}
    hb_human_id = data.get("hb_human_id")

    if not hb_human_id:
        return error_response("VALIDATION_ERROR", "hb_human_id is required", 400)

    from app.services.fantasy_draft_service import make_pick as _make_pick
    try:
        result = _make_pick(league_id, user.id, int(hb_human_id))
    except ValueError as e:
        return error_response("VALIDATION_ERROR", str(e), 400)
    except Exception as e:
        return error_response("INTERNAL_ERROR", str(e), 500)

    return jsonify(result)


@fantasy_bp.route("/leagues/<int:league_id>/draft/queue", methods=["GET"])
@optional_auth
def get_draft_queue(league_id: int):
    """GET /api/fantasy/leagues/<id>/draft/queue — full draft board."""
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None:
        return error_response("NOT_FOUND", "League not found", 404)

    stmt = (
        select(FantasyDraftQueue)
        .where(FantasyDraftQueue.league_id == league_id)
        .order_by(FantasyDraftQueue.overall_pick.asc())
    )
    picks = pred.execute(stmt).scalars().all()

    # Enrich with player name if picked
    human_names = {}
    if picks:
        picked_ids = [p.hb_human_id for p in picks if p.hb_human_id is not None]
        if picked_ids:
            from hockey_blast_common_lib.models import Human
            hb = HBSession()
            humans = hb.execute(
                select(Human).where(Human.id.in_(picked_ids))
            ).scalars().all()
            human_names = {h.id: f"{h.first_name} {h.last_name}".strip() for h in humans}

    # Manager names
    mgr_stmt = (
        select(FantasyManager, PredUser)
        .join(PredUser, FantasyManager.user_id == PredUser.id)
        .where(FantasyManager.league_id == league_id)
    )
    mgr_rows = pred.execute(mgr_stmt).all()
    mgr_map = {mgr.user_id: {"team_name": mgr.team_name, "display_name": user.display_name} for mgr, user in mgr_rows}

    queue = []
    for p in picks:
        d = p.to_dict()
        d["player_name"] = human_names.get(p.hb_human_id) if p.hb_human_id else None
        d["manager"] = mgr_map.get(p.user_id)
        queue.append(d)

    return jsonify({
        "league_id": league_id,
        "status": league.status,
        "queue": queue,
    })


@fantasy_bp.route("/leagues/<int:league_id>/roster/<int:user_id>", methods=["GET"])
@optional_auth
def get_roster(league_id: int, user_id: int):
    """GET /api/fantasy/leagues/<id>/roster/<user_id> — a manager's roster."""
    pred = PredSession()

    stmt = select(FantasyRoster).where(
        FantasyRoster.league_id == league_id,
        FantasyRoster.user_id == user_id,
    )
    roster = pred.execute(stmt).scalars().all()

    if not roster:
        return jsonify({"roster": []})

    # Enrich with player names
    human_ids = [r.hb_human_id for r in roster]
    from hockey_blast_common_lib.models import Human
    hb = HBSession()
    humans = hb.execute(select(Human).where(Human.id.in_(human_ids))).scalars().all()
    human_map = {h.id: h for h in humans}

    result = []
    for r in roster:
        d = r.to_dict()
        h = human_map.get(r.hb_human_id)
        if h:
            d["first_name"] = h.first_name
            d["last_name"] = h.last_name
            d["player_name"] = f"{h.first_name} {h.last_name}".strip()
        result.append(d)

    return jsonify({"roster": result})


@fantasy_bp.route("/leagues/<int:league_id>/standings", methods=["GET"])
@optional_auth
def get_standings(league_id: int):
    """GET /api/fantasy/leagues/<id>/standings — standings table."""
    pred = PredSession()

    stmt = (
        select(FantasyStandings, FantasyManager, PredUser)
        .join(FantasyManager, (FantasyManager.league_id == FantasyStandings.league_id) & (FantasyManager.user_id == FantasyStandings.user_id))
        .join(PredUser, PredUser.id == FantasyStandings.user_id)
        .where(FantasyStandings.league_id == league_id)
        .order_by(FantasyStandings.rank.asc().nullslast(), FantasyStandings.total_points.desc())
    )
    rows = pred.execute(stmt).all()

    standings = []
    for s, mgr, user in rows:
        d = s.to_dict()
        d["team_name"] = mgr.team_name
        d["display_name"] = user.display_name
        d["avatar_url"] = user.avatar_url
        standings.append(d)

    # If no standings yet, show managers with 0 pts
    if not standings:
        mgr_stmt = (
            select(FantasyManager, PredUser)
            .join(PredUser, FantasyManager.user_id == PredUser.id)
            .where(FantasyManager.league_id == league_id)
        )
        mgr_rows = pred.execute(mgr_stmt).all()
        for i, (mgr, user) in enumerate(mgr_rows, 1):
            standings.append({
                "league_id": league_id,
                "user_id": user.id,
                "total_points": 0.0,
                "week_points": 0.0,
                "rank": i,
                "team_name": mgr.team_name,
                "display_name": user.display_name,
                "avatar_url": user.avatar_url,
            })

    return jsonify({"standings": standings})


# ── Admin actions ─────────────────────────────────────────────────────────────

@fantasy_bp.route("/leagues/<int:league_id>/open-draft", methods=["POST"])
@require_auth
def open_draft(league_id: int):
    """POST /api/fantasy/leagues/<id>/open-draft — open the draft (creator only)."""
    pred = PredSession()
    user = g.pred_user
    league = pred.get(FantasyLeague, league_id)

    if league is None:
        return error_response("NOT_FOUND", "League not found", 404)
    if league.created_by != user.id:
        return error_response("FORBIDDEN", "Only the league creator can open the draft", 403)
    if league.status != "forming":
        return error_response("CONFLICT", f"League is already in status: {league.status}", 409)

    mgr_count = pred.execute(
        select(func.count()).select_from(FantasyManager).where(FantasyManager.league_id == league_id)
    ).scalar_one()
    if mgr_count < 2:
        return error_response("CONFLICT", "Need at least 2 managers to open draft", 409)

    # Assign random draft positions
    managers = pred.execute(
        select(FantasyManager).where(FantasyManager.league_id == league_id)
    ).scalars().all()
    positions = list(range(1, len(managers) + 1))
    random.shuffle(positions)
    for mgr, pos in zip(managers, positions):
        mgr.draft_position = pos

    league.status = "draft_open"
    pred.commit()

    # Build the draft queue
    from app.services.fantasy_draft_service import build_draft_queue
    try:
        build_draft_queue(league_id)
    except Exception as e:
        return error_response("INTERNAL_ERROR", f"Could not build draft queue: {e}", 500)

    return jsonify(league.to_dict())


@fantasy_bp.route("/leagues/<int:league_id>/start", methods=["POST"])
@require_auth
def start_season(league_id: int):
    """POST /api/fantasy/leagues/<id>/start — start the season (creator only)."""
    pred = PredSession()
    user = g.pred_user
    league = pred.get(FantasyLeague, league_id)

    if league is None:
        return error_response("NOT_FOUND", "League not found", 404)
    if league.created_by != user.id:
        return error_response("FORBIDDEN", "Only the league creator can start the season", 403)
    if league.status not in ("drafting", "draft_open"):
        return error_response("CONFLICT", f"Cannot start season from status: {league.status}", 409)

    league.status = "active"
    league.season_starts_at = datetime.now(timezone.utc)
    pred.commit()

    return jsonify(league.to_dict())

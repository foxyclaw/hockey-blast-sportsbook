"""
Games blueprint — browse upcoming pickable games from the hockey_blast DB.

GET  /api/games           — list upcoming games with filters + pagination
GET  /api/games/<game_id> — single game detail with current user's pick

Query budget: the hockey_blast DB is remote (~45 ms per round trip), so a page
of games must not issue per-game lookups.  ``build_game_maps`` resolves every
team / division / level / org / skill / pick for the page with one query per
table (fewer with warm caches, see app.services.hb_ref_data) and
``_serialize_game`` reads from those maps.
"""

import logging
from datetime import date, datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, func, or_, select

from app.auth.jwt_validator import optional_auth
from app.db import HBSession, PredSession
from app.services.hb_ref_data import get_divisions, get_orgs, get_team_names
from app.services.lock_checker import get_lock_deadline, is_game_pickable
from app.services.skill_snapshot import get_team_avg_skill, get_team_avg_skills
from app.utils.response import error_response

games_bp = Blueprint("games", __name__)
logger = logging.getLogger(__name__)


def _game_start_dt(game) -> datetime | None:
    """Combine game.date + game.time into a naive datetime."""
    game_date = getattr(game, "date", None)
    game_time = getattr(game, "time", None)
    if game_date is None:
        return None
    if game_time is not None:
        return datetime.combine(game_date, game_time)
    return datetime(game_date.year, game_date.month, game_date.day)


def _not_started_clause(Game, now: datetime):
    """
    SQL form of the old Python filter ``_game_start_dt(g) is None or _game_start_dt(g) >= now``.

    Callers already bound ``Game.date`` (so it is never NULL here):
      * date > today                         -> keep (NULL time = midnight, still ahead)
      * date == today and time >= now.time() -> keep
      * anything else (past day, or today with an earlier/NULL time) -> drop
    """
    today = now.date()
    return or_(Game.date > today, and_(Game.date == today, Game.time >= now.time()))


def _load_user_picks(game_ids, pred_user, pred_session) -> dict:
    """{game_id: PredPick} for the user's picks on these games — ONE pred-DB query."""
    from app.models.pred_pick import PredPick

    if not game_ids:
        return {}
    stmt = (
        select(PredPick)
        .where(PredPick.user_id == pred_user.id, PredPick.game_id.in_(game_ids))
        .order_by(PredPick.id.asc())
    )
    picks: dict = {}
    for pick in pred_session.execute(stmt).scalars():
        picks.setdefault(pick.game_id, pick)  # first (oldest) pick per game
    return picks


def _safe_load(loader, ids, hb_session) -> dict:
    """Run a batched reference loader; on failure behave like the old per-id helpers (None)."""
    try:
        return loader(ids, hb_session)
    except Exception:  # noqa: BLE001 — same swallow-all contract as _get_team & co.
        logger.warning("[games] batched %s lookup failed", loader.__name__, exc_info=True)
        return {}


def build_game_maps(games, hb_session, pred_user=None, pred_session=None) -> dict:
    """
    Pre-load everything ``_serialize_game`` needs for a page of games.

    Returns {"teams": {id: name}, "divisions": {id: dict|None}, "orgs": {id: dict|None},
             "skills": {team_id: float}, "picks": {game_id: PredPick}}  (picks only when
    a user is given).  Missing ids simply map to None / are absent.
    """
    team_ids: list = []
    skill_team_ids: list = []
    org_ids: list = []
    division_ids: list = []
    for game in games:
        team_ids.extend((game.home_team_id, game.visitor_team_id))
        org_id = getattr(game, "org_id", None)
        if org_id:
            org_ids.append(org_id)
            # skill is only computed for games with an org (see _serialize_game)
            skill_team_ids.extend((game.home_team_id, game.visitor_team_id))
        division_id = getattr(game, "division_id", None)
        if division_id:
            division_ids.append(division_id)

    maps = {
        "teams": _safe_load(get_team_names, team_ids, hb_session),
        "divisions": _safe_load(get_divisions, division_ids, hb_session),
        "orgs": _safe_load(get_orgs, org_ids, hb_session),
        "skills": get_team_avg_skills(skill_team_ids),
    }
    if pred_user and pred_session:
        maps["picks"] = _load_user_picks([game.id for game in games], pred_user, pred_session)
    return maps


def _serialize_game(game, hb_session, pred_user=None, pred_session=None, maps=None) -> dict:
    """
    Build JSON representation of a game.

    ``maps`` (from ``build_game_maps``) supplies the page-wide lookups so no
    per-game queries are issued.  Without it, falls back to the per-id helpers
    below (kept for other callers).
    """
    org_id = getattr(game, "org_id", None)
    division_id = getattr(game, "division_id", None)

    if maps is None:
        home_team = _get_team(game.home_team_id, hb_session)
        visitor_team = _get_team(game.visitor_team_id, hb_session)
        home_name = home_team.name if home_team else str(game.home_team_id)
        visitor_name = visitor_team.name if visitor_team else str(game.visitor_team_id)
        home_skill = get_team_avg_skill(game.home_team_id, org_id) if org_id else None
        visitor_skill = get_team_avg_skill(game.visitor_team_id, org_id) if org_id else None
        division = _get_division(division_id, hb_session)
        org = _get_org(org_id, hb_session)
    else:
        team_names = maps.get("teams", {})
        home_name = team_names.get(game.home_team_id)
        if home_name is None:
            home_name = str(game.home_team_id)
        visitor_name = team_names.get(game.visitor_team_id)
        if visitor_name is None:
            visitor_name = str(game.visitor_team_id)
        skills = maps.get("skills", {})
        home_skill = skills.get(game.home_team_id) if org_id else None
        visitor_skill = skills.get(game.visitor_team_id) if org_id else None
        division = maps.get("divisions", {}).get(division_id) if division_id else None
        org = maps.get("orgs", {}).get(org_id) if org_id else None

    # The game row is already in hand — no need for lock_checker to re-fetch it.
    is_pickable, lock_reason = is_game_pickable(game.id, game=game)
    lock_deadline = get_lock_deadline(game.id, game=game)
    scheduled = _game_start_dt(game)
    is_live = getattr(game, "live_time", None) is not None

    from app.services.odds_service import compute_odds

    odds = compute_odds(home_skill, visitor_skill)

    data = {
        "game_id": game.id,
        "scheduled_start": scheduled.isoformat() if scheduled else None,
        "lock_deadline": lock_deadline.isoformat() if lock_deadline else None,
        "status": getattr(game, "status", None),
        "is_pickable": is_pickable,
        "lock_reason": lock_reason if not is_pickable else None,
        "is_live": is_live,
        "org_id": org_id,
        "org": org,
        "division": division,
        "home_team": {
            "id": game.home_team_id,
            "name": home_name,
            "avg_skill": home_skill,
        },
        "away_team": {
            "id": game.visitor_team_id,
            "name": visitor_name,
            "avg_skill": visitor_skill,
        },
        "odds": odds,
    }

    if pred_user and pred_session:
        if maps is not None and "picks" in maps:
            user_pick = maps["picks"].get(game.id)
        else:
            from app.models.pred_pick import PredPick

            pick_stmt = (
                select(PredPick)
                .where(PredPick.user_id == pred_user.id, PredPick.game_id == game.id)
                .limit(1)
            )
            user_pick = pred_session.execute(pick_stmt).scalar_one_or_none()
        data["user_pick"] = user_pick.to_dict() if user_pick else None

    return data


def _get_team(team_id: int, hb_session):
    try:
        from hockey_blast_common_lib.models import Team

        stmt = select(Team).where(Team.id == team_id)
        return hb_session.execute(stmt).scalar_one_or_none()
    except Exception:
        return None


def _get_division(division_id: int | None, hb_session) -> dict | None:
    if not division_id:
        return None
    try:
        from hockey_blast_common_lib.models import Division, Level

        div = hb_session.execute(
            select(Division).where(Division.id == division_id)
        ).scalar_one_or_none()
        if not div:
            return None
        # Prefer Level.short_name (e.g. "4B", "O35"), fall back to div.level
        short_name = None
        if div.level_id:
            lvl = hb_session.execute(
                select(Level).where(Level.id == div.level_id)
            ).scalar_one_or_none()
            if lvl:
                short_name = lvl.short_name or lvl.level_name
        return {
            "id": div.id,
            "name": div.level,  # full name e.g. "Adult Division 4B"
            "short_name": short_name or div.level,  # e.g. "4B"
        }
    except Exception:
        pass
    return None


def _get_org(org_id: int | None, hb_session) -> dict | None:
    if not org_id:
        return None
    try:
        from hockey_blast_common_lib.models import Organization

        stmt = select(Organization).where(Organization.id == org_id)
        org = hb_session.execute(stmt).scalar_one_or_none()
        if org:
            return {"id": org.id, "name": org.organization_name}
    except Exception:
        pass
    return None


@games_bp.route("", methods=["GET"])
@optional_auth
def list_games():
    """GET /api/games — main game list, tracked as a visit event."""
    from app.services.event_tracker import track

    track(
        "visit",
        user_id=g.pred_user.id if g.pred_user else None,
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or "")
        .split(",")[0]
        .strip(),
    )
    try:
        from hockey_blast_common_lib.models import Game
        from hockey_blast_common_lib.game_status import StatusId
    except ImportError:
        return error_response("SERVICE_UNAVAILABLE", "Hockey Blast DB not available", 503)

    hb_session = HBSession()

    # Date range (Game.date is a date column, not datetime)
    try:
        today = date.today()
        from_date_str = request.args.get("from_date")
        to_date_str = request.args.get("to_date")
        from_dt = date.fromisoformat(from_date_str) if from_date_str else today
        to_dt = date.fromisoformat(to_date_str) if to_date_str else today + timedelta(days=7)
    except ValueError as exc:
        return error_response("VALIDATION_ERROR", f"Invalid date format: {exc}", 400)

    # Filter out games that have already started (today's past games) — in SQL,
    # so we never pull the whole window across the wire just to slice one page.
    now = datetime.now()
    conditions = [
        Game.status_id == StatusId.SCHEDULED,
        Game.date >= from_dt,
        Game.date <= to_dt,
        _not_started_clause(Game, now),
    ]

    org_id = request.args.get("org_id", type=int)
    division_id = request.args.get("division_id", type=int)

    if org_id:
        conditions.append(Game.org_id == org_id)
    if division_id:
        conditions.append(Game.division_id == division_id)

    page = max(1, request.args.get("page", 1, type=int))
    per_page = max(1, min(request.args.get("per_page", 20, type=int), 100))
    offset = (page - 1) * per_page

    # Count + fetch one page (Game.id tiebreak keeps pages stable for same-slot games)
    total = hb_session.execute(
        select(func.count()).select_from(Game).where(*conditions)
    ).scalar_one()
    stmt = (
        select(Game)
        .where(*conditions)
        .order_by(Game.date.asc(), Game.time.asc(), Game.id.asc())
        .offset(offset)
        .limit(per_page)
    )
    games = hb_session.execute(stmt).scalars().all()

    pred_user = g.pred_user
    pred_session = PredSession() if pred_user else None
    maps = build_game_maps(games, hb_session, pred_user, pred_session)

    return jsonify(
        {
            "games": [
                _serialize_game(gm, hb_session, pred_user, pred_session, maps=maps) for gm in games
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if total else 0,
        }
    )


@games_bp.route("/<int:game_id>", methods=["GET"])
@optional_auth
def get_game(game_id: int):
    """GET /api/games/<game_id> — single game detail."""
    try:
        from hockey_blast_common_lib.models import Game
    except ImportError:
        return error_response("SERVICE_UNAVAILABLE", "Hockey Blast DB not available", 503)

    hb_session = HBSession()
    stmt = select(Game).where(Game.id == game_id)
    game = hb_session.execute(stmt).scalar_one_or_none()

    if game is None:
        return error_response("NOT_FOUND", f"Game {game_id} not found", 404)

    pred_user = g.pred_user
    pred_session = PredSession() if pred_user else None
    maps = build_game_maps([game], hb_session, pred_user, pred_session)

    return jsonify(_serialize_game(game, hb_session, pred_user, pred_session, maps=maps))

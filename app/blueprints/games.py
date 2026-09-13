"""
Games blueprint — browse upcoming pickable games from the hockey_blast DB.

GET  /api/games           — list upcoming games with filters + pagination
GET  /api/games/<game_id> — single game detail with current user's pick

Query budget: the hockey_blast DB is remote (~45 ms per round trip), so a page
of games must not issue per-game lookups.  ``build_game_maps`` resolves every
team / division / level / org / skill / pick for the page with one query per
table (fewer with warm caches, see app.services.hb_ref_data) and
``_serialize_game`` reads only from those maps.
"""

import logging
from datetime import date, datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, func, or_, select

from app.auth.jwt_validator import optional_auth
from app.db import HBSession, PredSession
from app.services.hb_ref_data import (
    get_divisions,
    get_orgs,
    get_team_avg_skills_cached,
    get_team_names,
)
from app.services.lock_checker import _game_start_dt, get_lock_deadline, is_game_pickable
from app.utils.response import error_response

games_bp = Blueprint("games", __name__)
logger = logging.getLogger(__name__)

# join_code of the auto-joined default league (see picks._get_or_create_global_league)
GLOBAL_LEAGUE_JOIN_CODE = "GLOBAL01"


def _not_started_clause(Game, now: datetime):
    """
    SQL twin of ``lock_checker._game_start_dt(g) >= now`` (the Python filter this
    endpoint used to apply after fetching the whole window).  Keep the two in sync;
    tests/unit/test_games_batched.py checks they agree row-for-row.

    Callers already bound ``Game.date`` (so it is never NULL here):
      * date > today                         -> keep (NULL time = midnight, still ahead)
      * date == today and time >= now.time() -> keep
      * anything else (past day, or today with an earlier/NULL time) -> drop
    """
    today = now.date()
    return or_(Game.date > today, and_(Game.date == today, Game.time >= now.time()))


def _load_user_picks(game_ids, pred_user, pred_session) -> dict:
    """
    {game_id: PredPick} for the user's picks on these games — ONE pred-DB query.

    A user can hold one pick per league on the same game; the pick shown on the
    games list is the GLOBAL league's, falling back to the oldest (lowest id).
    """
    from app.models.pred_league import PredLeague
    from app.models.pred_pick import PredPick

    if not game_ids:
        return {}
    stmt = (
        select(PredPick, PredLeague.join_code)
        .join(PredLeague, PredPick.league_id == PredLeague.id)
        .where(PredPick.user_id == pred_user.id, PredPick.game_id.in_(game_ids))
        .order_by(PredPick.id.asc())
    )
    picks: dict = {}
    for pick, join_code in pred_session.execute(stmt).all():
        if join_code == GLOBAL_LEAGUE_JOIN_CODE:
            picks[pick.game_id] = pick
        else:
            picks.setdefault(pick.game_id, pick)
    return picks


def _safe_load(loader, ids, hb_session) -> dict:
    """
    Run a batched reference loader; on failure log, roll back the (now aborted)
    HB transaction so later queries in the request still work, and return {} so
    the page degrades (None names/skills) instead of 500ing.
    """
    try:
        return loader(ids, hb_session)
    except Exception:  # noqa: BLE001
        logger.warning("[games] batched %s lookup failed", loader.__name__, exc_info=True)
        try:
            hb_session.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("[games] rollback after failed lookup also failed", exc_info=True)
        return {}


def build_game_maps(games, hb_session, pred_user=None, pred_session=None) -> dict:
    """
    Pre-load everything ``_serialize_game`` needs for a page of games.

    Returns {"teams": {id: name}, "divisions": {id: dict|None}, "orgs": {id: dict|None},
             "skills": {team_id: float|None}, "picks": {game_id: PredPick}}.
    ``picks`` is {} for anonymous requests.  Missing ids map to None / are absent.
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
        "skills": _safe_load(get_team_avg_skills_cached, skill_team_ids, hb_session),
        "picks": {},
    }
    if pred_user and pred_session:
        maps["picks"] = _load_user_picks([game.id for game in games], pred_user, pred_session)
    return maps


def _serialize_game(game, maps, pred_user=None) -> dict:
    """
    Build JSON representation of a game from the page-wide ``maps``
    (see ``build_game_maps``).  Issues no queries of its own.
    """
    org_id = getattr(game, "org_id", None)
    division_id = getattr(game, "division_id", None)

    team_names = maps["teams"]
    home_name = team_names.get(game.home_team_id)
    if home_name is None:
        home_name = str(game.home_team_id)
    visitor_name = team_names.get(game.visitor_team_id)
    if visitor_name is None:
        visitor_name = str(game.visitor_team_id)
    skills = maps["skills"]
    home_skill = skills.get(game.home_team_id) if org_id else None
    visitor_skill = skills.get(game.visitor_team_id) if org_id else None
    division = maps["divisions"].get(division_id) if division_id else None
    org = maps["orgs"].get(org_id) if org_id else None

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

    if pred_user:
        user_pick = maps["picks"].get(game.id)
        data["user_pick"] = user_pick.to_dict() if user_pick else None

    return data


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
            "games": [_serialize_game(gm, maps, pred_user) for gm in games],
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

    return jsonify(_serialize_game(game, maps, pred_user))

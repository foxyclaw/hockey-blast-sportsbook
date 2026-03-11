"""
Games blueprint — browse upcoming pickable games from the hockey_blast DB.

GET  /api/games           — list upcoming games with filters + pagination
GET  /api/games/<game_id> — single game detail with current user's pick
"""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, select

from app.auth.jwt_validator import optional_auth
from app.db import HBSession, PredSession
from app.services.lock_checker import get_lock_deadline, is_game_pickable
from app.services.skill_snapshot import get_team_avg_skill
from app.utils.pagination import paginate_query
from app.utils.response import error_response

games_bp = Blueprint("games", __name__)


def _serialize_game(game, hb_session, pred_user=None, pred_session=None) -> dict:
    """
    Build the JSON representation of a game with skill data.
    Optionally includes the current user's pick if pred_user is given.
    """
    # Get team info — try to load Team objects, fall back to IDs
    home_team = _get_team(game.home_team_id, hb_session)
    away_team = _get_team(game.away_team_id, hb_session)

    # Skill data — try to get org_id from game or season
    org_id = _get_org_id(game, hb_session)

    home_skill = None
    away_skill = None
    if org_id:
        home_skill = get_team_avg_skill(game.home_team_id, org_id)
        away_skill = get_team_avg_skill(game.away_team_id, org_id)

    # Lock info
    is_pickable, lock_reason = is_game_pickable(game.id)
    lock_deadline = get_lock_deadline(game.id)

    scheduled = getattr(game, "game_date_time", None)
    if scheduled and scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)

    is_live = getattr(game, "live_time", None) is not None

    data = {
        "game_id": game.id,
        "scheduled_start": scheduled.isoformat() if scheduled else None,
        "lock_deadline": lock_deadline.isoformat() if lock_deadline else None,
        "status": getattr(game, "status", None),
        "is_pickable": is_pickable,
        "is_live": is_live,
        "home_team": {
            "id": game.home_team_id,
            "name": home_team.name if home_team else str(game.home_team_id),
            "avg_skill": home_skill,
        },
        "away_team": {
            "id": game.away_team_id,
            "name": away_team.name if away_team else str(game.away_team_id),
            "avg_skill": away_skill,
        },
    }

    # Division/org info if available
    if org_id:
        data["org"] = {"id": org_id}

    # User's pick in this game (across all leagues — returns first found)
    if pred_user and pred_session:
        from app.models.pred_pick import PredPick

        pick_stmt = select(PredPick).where(
            PredPick.user_id == pred_user.id,
            PredPick.game_id == game.id,
        ).limit(1)
        user_pick = pred_session.execute(pick_stmt).scalar_one_or_none()
        data["user_pick"] = user_pick.to_dict() if user_pick else None

    return data


def _get_team(team_id: int, hb_session):
    """Fetch a Team object, return None if not available."""
    try:
        from hockey_blast_common_lib.models import Team
        stmt = select(Team).where(Team.id == team_id)
        return hb_session.execute(stmt).scalar_one_or_none()
    except (ImportError, Exception):
        return None


def _get_org_id(game, hb_session) -> int | None:
    """Attempt to determine org_id from the game."""
    org_id = getattr(game, "org_id", None)
    if org_id:
        return org_id
    # Try via season
    try:
        season = getattr(game, "season", None)
        if season:
            return getattr(season, "org_id", None)
    except Exception:
        pass
    return None


@games_bp.route("", methods=["GET"])
@optional_auth
def list_games():
    """
    GET /api/games

    Query params:
        org_id       — filter by organization
        division_id  — filter by division
        season_id    — filter by season
        from_date    — ISO date string (default: today UTC)
        to_date      — ISO date string (default: today + 7 days)
        page         — page number (default: 1)
        per_page     — page size (default: 20, max: 100)
    """
    try:
        from hockey_blast_common_lib.models import Game
    except ImportError:
        return error_response("SERVICE_UNAVAILABLE", "Hockey Blast DB not available", 503)

    hb_session = HBSession()

    # Date range filters
    try:
        now_utc = datetime.now(timezone.utc)
        from_date_str = request.args.get("from_date")
        to_date_str = request.args.get("to_date")

        from_dt = (
            datetime.fromisoformat(from_date_str).replace(tzinfo=timezone.utc)
            if from_date_str
            else now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        )
        to_dt = (
            datetime.fromisoformat(to_date_str).replace(tzinfo=timezone.utc)
            if to_date_str
            else from_dt + timedelta(days=7)
        )
    except ValueError as exc:
        return error_response("VALIDATION_ERROR", f"Invalid date format: {exc}", 400)

    # Build query
    stmt = select(Game).where(
        Game.status == "Scheduled",
        Game.game_date_time >= from_dt,
        Game.game_date_time <= to_dt,
    )

    # Optional filters
    org_id = request.args.get("org_id", type=int)
    division_id = request.args.get("division_id", type=int)
    season_id = request.args.get("season_id", type=int)

    if org_id:
        stmt = stmt.where(Game.org_id == org_id)
    if division_id and hasattr(Game, "division_id"):
        stmt = stmt.where(Game.division_id == division_id)
    if season_id and hasattr(Game, "season_id"):
        stmt = stmt.where(Game.season_id == season_id)

    stmt = stmt.order_by(Game.game_date_time.asc())

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    total_stmt = stmt.with_only_columns(Game.id)
    all_ids = hb_session.execute(total_stmt).scalars().all()
    total = len(all_ids)

    offset = (page - 1) * per_page
    games = hb_session.execute(stmt.offset(offset).limit(per_page)).scalars().all()

    pred_user = g.pred_user
    pred_session = PredSession() if pred_user else None

    return jsonify({
        "games": [_serialize_game(g_obj, hb_session, pred_user, pred_session) for g_obj in games],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    })


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

    return jsonify(_serialize_game(game, hb_session, pred_user, pred_session))

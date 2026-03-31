"""
Games blueprint — browse upcoming pickable games from the hockey_blast DB.

GET  /api/games           — list upcoming games with filters + pagination
GET  /api/games/<game_id> — single game detail with current user's pick
"""

from datetime import date, datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, select

from app.auth.jwt_validator import optional_auth
from app.db import HBSession, PredSession
from app.services.lock_checker import get_lock_deadline, is_game_pickable
from app.services.skill_snapshot import get_team_avg_skill
from app.utils.response import error_response

games_bp = Blueprint("games", __name__)


def _game_start_dt(game) -> datetime | None:
    """Combine game.date + game.time into a naive datetime."""
    game_date = getattr(game, "date", None)
    game_time = getattr(game, "time", None)
    if game_date is None:
        return None
    if game_time is not None:
        return datetime.combine(game_date, game_time)
    return datetime(game_date.year, game_date.month, game_date.day)


def _serialize_game(game, hb_session, pred_user=None, pred_session=None) -> dict:
    """Build JSON representation of a game."""
    home_team = _get_team(game.home_team_id, hb_session)
    visitor_team = _get_team(game.visitor_team_id, hb_session)

    org_id = getattr(game, "org_id", None)
    home_skill = get_team_avg_skill(game.home_team_id, org_id) if org_id else None
    visitor_skill = get_team_avg_skill(game.visitor_team_id, org_id) if org_id else None
    division = _get_division(getattr(game, "division_id", None), hb_session)

    is_pickable, lock_reason = is_game_pickable(game.id)
    lock_deadline = get_lock_deadline(game.id)
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
        "org": _get_org(org_id, hb_session),
        "division": division,
        "home_team": {
            "id": game.home_team_id,
            "name": home_team.name if home_team else str(game.home_team_id),
            "avg_skill": home_skill,
        },
        "away_team": {
            "id": game.visitor_team_id,
            "name": visitor_team.name if visitor_team else str(game.visitor_team_id),
            "avg_skill": visitor_skill,
        },
        "odds": odds,
    }

    if pred_user and pred_session:
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
        div = hb_session.execute(select(Division).where(Division.id == division_id)).scalar_one_or_none()
        if not div:
            return None
        # Prefer Level.short_name (e.g. "4B", "O35"), fall back to div.level
        short_name = None
        if div.level_id:
            lvl = hb_session.execute(select(Level).where(Level.id == div.level_id)).scalar_one_or_none()
            if lvl:
                short_name = lvl.short_name or lvl.level_name
        return {
            "id": div.id,
            "name": div.level,          # full name e.g. "Adult Division 4B"
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
    track("visit", user_id=g.pred_user.id if g.pred_user else None, ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip())
    try:
        from hockey_blast_common_lib.models import Game
    except ImportError:
        return error_response("SERVICE_UNAVAILABLE", "Hockey Blast DB not available", 503)

    hb_session = HBSession()

    # Date range (Game.date is a date column, not datetime)
    try:
        today = date.today()
        from_date_str = request.args.get("from_date")
        to_date_str = request.args.get("to_date")
        from_dt = (
            date.fromisoformat(from_date_str) if from_date_str else today
        )
        to_dt = (
            date.fromisoformat(to_date_str)
            if to_date_str
            else today + timedelta(days=7)
        )
    except ValueError as exc:
        return error_response("VALIDATION_ERROR", f"Invalid date format: {exc}", 400)

    stmt = select(Game).where(
        Game.status == "Scheduled",
        Game.date >= from_dt,
        Game.date <= to_dt,
    )

    org_id = request.args.get("org_id", type=int)
    division_id = request.args.get("division_id", type=int)

    if org_id:
        stmt = stmt.where(Game.org_id == org_id)
    if division_id:
        stmt = stmt.where(Game.division_id == division_id)

    stmt = stmt.order_by(Game.date.asc(), Game.time.asc())

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    offset = (page - 1) * per_page

    # Count + fetch
    all_games = hb_session.execute(stmt).scalars().all()

    # Filter out games that have already started (today's past games)
    now = datetime.now()
    all_games = [
        gm for gm in all_games
        if _game_start_dt(gm) is None or _game_start_dt(gm) >= now
    ]

    total = len(all_games)
    games = all_games[offset : offset + per_page]

    pred_user = g.pred_user
    pred_session = PredSession() if pred_user else None

    return jsonify(
        {
            "games": [
                _serialize_game(gm, hb_session, pred_user, pred_session)
                for gm in games
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

    return jsonify(_serialize_game(game, hb_session, pred_user, pred_session))

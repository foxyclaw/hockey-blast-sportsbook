"""
Standings blueprint.

GET /api/standings/<league_id>  — full leaderboard for a league
"""

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from app.auth.jwt_validator import require_auth
from app.db import PredSession
from app.models.pred_league import PredLeague
from app.models.pred_league_member import PredLeagueMember
from app.models.pred_league_standings import PredLeagueStandings
from app.models.pred_user import PredUser
from app.utils.response import error_response

standings_bp = Blueprint("standings", __name__)


@standings_bp.route("/<int:league_id>", methods=["GET"])
@require_auth
def get_standings(league_id: int):
    """
    GET /api/standings/<league_id>

    Returns the full leaderboard for a league.
    Only accessible to league members.
    """
    pred_session = PredSession()
    user = g.pred_user

    league = pred_session.get(PredLeague, league_id)
    if league is None or not league.is_active:
        return error_response("NOT_FOUND", "League not found", 404)

    # Membership check
    member_stmt = select(PredLeagueMember).where(
        PredLeagueMember.user_id == user.id,
        PredLeagueMember.league_id == league_id,
        PredLeagueMember.is_active == True,  # noqa: E712
    )
    if pred_session.execute(member_stmt).scalar_one_or_none() is None:
        return error_response("FORBIDDEN", "You are not a member of this league", 403)

    # Fetch standings with user data
    stmt = (
        select(PredLeagueStandings, PredUser)
        .join(PredUser, PredLeagueStandings.user_id == PredUser.id)
        .where(PredLeagueStandings.league_id == league_id)
        .order_by(
            PredLeagueStandings.rank.asc().nulls_last(),
            PredLeagueStandings.total_points.desc(),
        )
    )
    rows = pred_session.execute(stmt).all()

    standings_data = []
    last_updated = None

    for standings, standings_user in rows:
        entry = standings.to_dict()
        entry["display_name"] = standings_user.display_name
        entry["avatar_url"] = standings_user.avatar_url
        entry["balance"] = standings_user.balance
        entry["user"] = {
            "id": standings_user.id,
            "display_name": standings_user.display_name,
            "avatar_url": standings_user.avatar_url,
        }
        standings_data.append(entry)
        if last_updated is None or (
            standings.last_updated_at and standings.last_updated_at > last_updated
        ):
            last_updated = standings.last_updated_at

    return jsonify({
        "league_id": league_id,
        "league_name": league.name,
        "standings": standings_data,
        "last_updated_at": last_updated.isoformat() if last_updated else None,
    })

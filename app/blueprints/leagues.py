"""
Leagues blueprint.

POST  /api/leagues              — create a new league
GET   /api/leagues/<id>         — league detail
POST  /api/leagues/join         — join a league via join code
GET   /api/leagues/<id>/members — list league members
GET   /api/leagues/<id>/picks   — all picks in league for a game (post-lock only)
"""

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select, func

from app.auth.jwt_validator import require_auth
from app.db import PredSession
from app.models.pred_league import PredLeague, LeagueScope
from app.models.pred_league_member import PredLeagueMember, MemberRole
from app.models.pred_pick import PredPick
from app.models.pred_user import PredUser
from app.services.lock_checker import is_game_pickable
from app.utils.response import error_response

leagues_bp = Blueprint("leagues", __name__)


@leagues_bp.route("", methods=["POST"])
@require_auth
def create_league():
    """
    POST /api/leagues

    Body:
        name                          str   required
        description                   str   optional
        scope                         str   "all_orgs"|"org"|"division"|"custom" (default: "all_orgs")
        org_id                        int   optional (required if scope=org)
        division_id                   int   optional (required if scope=division)
        season_id                     int   optional
        max_members                   int   optional (default: 50)
        upset_bonus_enabled           bool  optional (default: true)
        confidence_multiplier_enabled bool  optional (default: true)
        correct_pick_base_points      int   optional (default: 10)
    """
    data = request.get_json(force=True, silent=True) or {}

    if not data.get("name"):
        return error_response("VALIDATION_ERROR", "League name is required", 400)

    name = data["name"].strip()
    if len(name) > 128:
        return error_response("VALIDATION_ERROR", "League name must be 128 characters or less", 400)

    # Validate scope
    scope_str = data.get("scope", "all_orgs")
    try:
        scope = LeagueScope(scope_str)
    except ValueError:
        valid = [s.value for s in LeagueScope]
        return error_response("VALIDATION_ERROR", f"scope must be one of: {valid}", 400)

    if scope == LeagueScope.ORG and not data.get("org_id"):
        return error_response("VALIDATION_ERROR", "org_id required when scope=org", 400)
    if scope == LeagueScope.DIVISION and not data.get("division_id"):
        return error_response("VALIDATION_ERROR", "division_id required when scope=division", 400)

    pred_session = PredSession()
    user = g.pred_user

    try:
        league = PredLeague(
            name=name,
            description=data.get("description"),
            season_label=data.get("season_label"),
            scope=scope,
            org_id=data.get("org_id"),
            division_id=data.get("division_id"),
            season_id=data.get("season_id"),
            commissioner_id=user.id,
            max_members=data.get("max_members", 50),
            upset_bonus_enabled=data.get("upset_bonus_enabled", True),
            confidence_multiplier_enabled=data.get("confidence_multiplier_enabled", True),
            correct_pick_base_points=data.get("correct_pick_base_points", 10),
        )
        pred_session.add(league)
        pred_session.flush()  # Get the league ID

        # Add commissioner as first member
        membership = PredLeagueMember(
            user_id=user.id,
            league_id=league.id,
            role=MemberRole.COMMISSIONER,
        )
        pred_session.add(membership)
        pred_session.commit()
        pred_session.refresh(league)

    except Exception as exc:
        pred_session.rollback()
        return error_response("INTERNAL_ERROR", str(exc), 500)

    data = league.to_dict()
    data["member_count"] = 1
    return jsonify(data), 201


@leagues_bp.route("/join", methods=["POST"])
@require_auth
def join_league():
    """
    POST /api/leagues/join

    Body:
        join_code  str  required
    """
    data = request.get_json(force=True, silent=True) or {}
    join_code = (data.get("join_code") or "").strip().upper()

    if not join_code:
        return error_response("VALIDATION_ERROR", "join_code is required", 400)

    pred_session = PredSession()
    user = g.pred_user

    # Find the league
    stmt = select(PredLeague).where(
        PredLeague.join_code == join_code,
        PredLeague.is_active == True,  # noqa: E712
    )
    league = pred_session.execute(stmt).scalar_one_or_none()

    if league is None:
        return error_response("NOT_FOUND", "League not found with that join code", 404)

    # Check if already a member
    member_stmt = select(PredLeagueMember).where(
        PredLeagueMember.user_id == user.id,
        PredLeagueMember.league_id == league.id,
    )
    existing = pred_session.execute(member_stmt).scalar_one_or_none()

    if existing:
        if existing.is_active:
            return error_response("ALREADY_MEMBER", "You are already a member of this league", 409)
        else:
            # Re-activate
            existing.is_active = True
            pred_session.commit()
            return jsonify(league.to_dict())

    # Check member limit
    active_member_stmt = select(PredLeagueMember).where(
        PredLeagueMember.league_id == league.id,
        PredLeagueMember.is_active == True,  # noqa: E712
    )
    active_count = len(pred_session.execute(active_member_stmt).scalars().all())

    if active_count >= league.max_members:
        return error_response("LEAGUE_FULL", "This league has reached its maximum membership", 409)

    try:
        membership = PredLeagueMember(
            user_id=user.id,
            league_id=league.id,
            role=MemberRole.MEMBER,
        )
        pred_session.add(membership)
        pred_session.commit()
    except Exception as exc:
        pred_session.rollback()
        return error_response("INTERNAL_ERROR", str(exc), 500)

    return jsonify(league.to_dict())


@leagues_bp.route("/<int:league_id>", methods=["GET"])
@require_auth
def get_league(league_id: int):
    """GET /api/leagues/<league_id> — league detail."""
    pred_session = PredSession()
    user = g.pred_user

    league = pred_session.get(PredLeague, league_id)
    if league is None or not league.is_active:
        return error_response("NOT_FOUND", "League not found", 404)

    # Check membership (only members can view league details)
    member_stmt = select(PredLeagueMember).where(
        PredLeagueMember.user_id == user.id,
        PredLeagueMember.league_id == league_id,
        PredLeagueMember.is_active == True,  # noqa: E712
    )
    membership = pred_session.execute(member_stmt).scalar_one_or_none()

    if membership is None and not league.is_public:
        return error_response("FORBIDDEN", "You are not a member of this league", 403)

    # Count members
    member_count_stmt = select(PredLeagueMember).where(
        PredLeagueMember.league_id == league_id,
        PredLeagueMember.is_active == True,  # noqa: E712
    )
    member_count = len(pred_session.execute(member_count_stmt).scalars().all())

    # Get commissioner info
    commissioner = pred_session.get(PredUser, league.commissioner_id)

    data = league.to_dict()
    data["member_count"] = member_count
    data["commissioner"] = {
        "id": commissioner.id,
        "display_name": commissioner.display_name,
        "avatar_url": commissioner.avatar_url,
    } if commissioner else None
    data["is_member"] = membership is not None
    data["is_commissioner"] = membership is not None and membership.role == MemberRole.COMMISSIONER

    return jsonify(data)


@leagues_bp.route("/<int:league_id>/members", methods=["GET"])
@require_auth
def list_members(league_id: int):
    """GET /api/leagues/<league_id>/members"""
    pred_session = PredSession()
    user = g.pred_user

    league = pred_session.get(PredLeague, league_id)
    if league is None:
        return error_response("NOT_FOUND", "League not found", 404)

    # Check membership
    member_stmt = select(PredLeagueMember).where(
        PredLeagueMember.user_id == user.id,
        PredLeagueMember.league_id == league_id,
        PredLeagueMember.is_active == True,  # noqa: E712
    )
    if pred_session.execute(member_stmt).scalar_one_or_none() is None:
        return error_response("FORBIDDEN", "You are not a member of this league", 403)

    all_members_stmt = (
        select(PredLeagueMember, PredUser)
        .join(PredUser, PredLeagueMember.user_id == PredUser.id)
        .where(
            PredLeagueMember.league_id == league_id,
            PredLeagueMember.is_active == True,  # noqa: E712
        )
        .order_by(PredLeagueMember.joined_at.asc())
    )
    rows = pred_session.execute(all_members_stmt).all()

    members = []
    for member, member_user in rows:
        members.append({
            "user_id": member_user.id,
            "display_name": member_user.display_name,
            "avatar_url": member_user.avatar_url,
            "role": member.role.value,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        })

    return jsonify({"league_id": league_id, "members": members})


@leagues_bp.route("/<int:league_id>/picks", methods=["GET"])
@require_auth
def league_game_picks(league_id: int):
    """
    GET /api/leagues/<league_id>/picks?game_id=<game_id>

    Returns all picks for a game in this league.
    Other users' picks are only visible after the game locks.
    """
    pred_session = PredSession()
    user = g.pred_user

    game_id = request.args.get("game_id", type=int)
    if not game_id:
        return error_response("VALIDATION_ERROR", "game_id query param is required", 400)

    # Membership check
    member_stmt = select(PredLeagueMember).where(
        PredLeagueMember.user_id == user.id,
        PredLeagueMember.league_id == league_id,
        PredLeagueMember.is_active == True,  # noqa: E712
    )
    if pred_session.execute(member_stmt).scalar_one_or_none() is None:
        return error_response("FORBIDDEN", "You are not a member of this league", 403)

    # Determine visibility
    is_pickable, _ = is_game_pickable(game_id)
    game_is_locked = not is_pickable

    stmt = (
        select(PredPick, PredUser)
        .join(PredUser, PredPick.user_id == PredUser.id)
        .where(
            PredPick.league_id == league_id,
            PredPick.game_id == game_id,
        )
    )

    rows = pred_session.execute(stmt).all()

    picks_data = []
    for pick, pick_user in rows:
        if not game_is_locked and pick.user_id != user.id:
            # Hide other users' picks before lock
            picks_data.append({
                "user_id": pick_user.id,
                "display_name": pick_user.display_name,
                "avatar_url": pick_user.avatar_url,
                "pick_hidden": True,
                "message": "Pick hidden until game locks",
            })
        else:
            pick_dict = pick.to_dict()
            pick_dict["display_name"] = pick_user.display_name
            pick_dict["avatar_url"] = pick_user.avatar_url
            if pick.result:
                pick_dict["result"] = pick.result.to_dict()
            picks_data.append(pick_dict)

    return jsonify({
        "league_id": league_id,
        "game_id": game_id,
        "game_locked": game_is_locked,
        "picks": picks_data,
    })


@leagues_bp.route("/mine", methods=["GET"])
@require_auth
def my_leagues():
    """GET /api/leagues/mine — leagues the current user belongs to."""
    pred_session = PredSession()
    user = g.pred_user

    stmt = (
        select(PredLeague)
        .join(PredLeagueMember, PredLeagueMember.league_id == PredLeague.id)
        .where(PredLeagueMember.user_id == user.id, PredLeagueMember.is_active == True)  # noqa: E712
        .order_by(PredLeague.created_at.desc())
    )
    leagues = pred_session.execute(stmt).scalars().all()

    result = []
    for league in leagues:
        # Member count
        member_count_stmt = select(func.count()).select_from(PredLeagueMember).where(
            PredLeagueMember.league_id == league.id,
            PredLeagueMember.is_active == True,  # noqa: E712
        )
        member_count = pred_session.execute(member_count_stmt).scalar_one()
        d = league.to_dict() if hasattr(league, "to_dict") else {"id": league.id, "name": league.name}
        d["member_count"] = member_count
        result.append(d)

    return jsonify({"leagues": result})

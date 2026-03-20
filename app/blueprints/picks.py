"""
Picks blueprint.

POST   /api/picks                  — submit or update a pick
GET    /api/picks/mine             — current user's picks (with optional filters)
DELETE /api/picks/<pick_id>        — retract a pick (if game not locked)
GET    /api/picks/<pick_id>        — single pick detail
"""

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from app.auth.jwt_validator import require_auth
from app.db import HBSession, PredSession
from app.models.pred_league import PredLeague
from app.models.pred_pick import PredPick
from app.models.pred_result import PredResult
from app.services.pick_service import (
    PickError,
    compute_projected_points,
    retract_pick,
    submit_pick,
)
from app.services.lock_checker import get_lock_deadline
from app.utils.response import error_response


def _team_name(team_id: int, hb_session) -> str | None:
    """Fetch team name from hockey_blast DB; returns None on failure."""
    if not team_id:
        return None
    try:
        from hockey_blast_common_lib.models import Team
        team = hb_session.execute(select(Team).where(Team.id == team_id)).scalar_one_or_none()
        return team.name if team else None
    except Exception:
        return None


def _enrich_pick(pick, hb_session) -> dict:
    """Serialize a PredPick with computed display fields."""
    d = pick.to_dict()

    # Team names
    home_name = _team_name(pick.home_team_id, hb_session)
    away_name = _team_name(pick.away_team_id, hb_session)
    picked_name = _team_name(pick.picked_team_id, hb_session)
    d["home_team_name"] = home_name
    d["away_team_name"] = away_name
    d["picked_team_name"] = picked_name

    # Status + points — time-based: pending → live (started) → graded
    if pick.result:
        d["result"] = pick.result.to_dict()
        d["status"] = "graded"
        d["points_earned"] = pick.result.total_points
    elif d.get("is_started"):
        d["status"] = "live"
        d["points_earned"] = None
    else:
        d["status"] = "pending"
        d["points_earned"] = None

    return d

picks_bp = Blueprint("picks", __name__)

GLOBAL_LEAGUE_NAME = "🌎 Global Picks"
GLOBAL_LEAGUE_JOIN_CODE = "GLOBAL01"


def _get_or_create_global_league(user, pred_session) -> int:
    """Return (creating if needed) the global default league ID, auto-joining the user."""
    from app.models.pred_league import PredLeague, LeagueScope
    from app.models.pred_league_member import PredLeagueMember, MemberRole

    # Find or create global league
    league = pred_session.execute(
        select(PredLeague).where(PredLeague.join_code == GLOBAL_LEAGUE_JOIN_CODE)
    ).scalar_one_or_none()

    if not league:
        league = PredLeague(
            name=GLOBAL_LEAGUE_NAME,
            join_code=GLOBAL_LEAGUE_JOIN_CODE,
            scope=LeagueScope.ALL_ORGS,
            commissioner_id=user.id,
            max_members=10000,
            is_public=True,
        )
        pred_session.add(league)
        pred_session.flush()

    # Auto-join if not already a member
    existing = pred_session.execute(
        select(PredLeagueMember).where(
            PredLeagueMember.user_id == user.id,
            PredLeagueMember.league_id == league.id,
        )
    ).scalar_one_or_none()

    if not existing:
        pred_session.add(PredLeagueMember(
            user_id=user.id,
            league_id=league.id,
            role=MemberRole.MEMBER,
        ))
        pred_session.flush()

    return league.id


@picks_bp.route("", methods=["POST"])
@require_auth
def create_pick():
    """
    POST /api/picks

    Body:
        game_id        int   required
        league_id      int   required
        picked_team_id int   required
        confidence     int   1|2|3  (default: 1)

    Returns 201 on success, 409 if locked, 400 on validation errors.
    """
    data = request.get_json(force=True, silent=True) or {}

    # Validate required fields
    missing = [f for f in ("game_id", "picked_team_id") if f not in data]
    if missing:
        return error_response(
            "VALIDATION_ERROR", f"Missing required fields: {', '.join(missing)}", 400
        )

    game_id = data["game_id"]
    picked_team_id = data["picked_team_id"]
    confidence = data.get("confidence", 1)
    wager = data.get("wager", None)

    if confidence not in (1, 2, 3):
        return error_response("VALIDATION_ERROR", "Confidence must be 1, 2, or 3", 400)

    if wager is not None:
        if not isinstance(wager, int) or wager < 1 or wager > 500:
            return error_response("VALIDATION_ERROR", "Wager must be an integer between 1 and 500", 400)

    pred_session = PredSession()
    user = g.pred_user

    # If no league_id provided, auto-join the global default league
    league_id = data.get("league_id")
    if not league_id:
        league_id = _get_or_create_global_league(user, pred_session)

    import logging
    logging.getLogger(__name__).info(
        f"[Pick] user={user.id} game={game_id} team={picked_team_id} league={league_id} confidence={confidence}"
    )

    try:
        pick = submit_pick(
            user=user,
            game_id=game_id,
            league_id=league_id,
            picked_team_id=picked_team_id,
            confidence=confidence,
            pred_session=pred_session,
            wager=wager,
        )
        pred_session.commit()
        pred_session.refresh(pick)
    except PickError as exc:
        pred_session.rollback()
        return error_response(exc.code, exc.message, exc.http_status)
    except Exception as exc:
        pred_session.rollback()
        return error_response("INTERNAL_ERROR", str(exc), 500)

    # Compute projected points
    league_stmt = select(PredLeague).where(PredLeague.id == league_id)
    league = pred_session.execute(league_stmt).scalar_one_or_none()
    projected = compute_projected_points(pick, league) if league else {"correct": 0, "wrong": 0}

    lock_deadline = get_lock_deadline(game_id)

    # Reload user to get fresh balance
    pred_session.refresh(user)

    # Reload db_user to get fresh balance after wager deduction
    from app.models.pred_user import PredUser as PredUserModel
    fresh_user = pred_session.get(PredUserModel, user.id)

    from app.services.event_tracker import track
    track("pick", user_id=user.id, ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip())

    return jsonify({
        "pick_id": pick.id,
        "game_id": pick.game_id,
        "league_id": pick.league_id,
        "picked_team_id": pick.picked_team_id,
        "confidence": pick.confidence,
        "wager": pick.wager,
        "odds_at_pick": float(pick.odds_at_pick) if pick.odds_at_pick is not None else None,
        "effective_wager": pick.effective_wager,
        "potential_payout": pick.potential_payout,
        "is_upset_pick": pick.is_upset_pick,
        "skill_differential": (
            float(pick.skill_differential) if pick.skill_differential is not None else None
        ),
        "projected_points": projected,
        "lock_deadline": lock_deadline.isoformat() if lock_deadline else None,
        "balance": fresh_user.balance if fresh_user else user.balance,
    }), 201


@picks_bp.route("/mine", methods=["GET"])
@require_auth
def my_picks():
    """
    GET /api/picks/mine

    Query params:
        league_id   — filter by league
        status      — "pending" | "graded" | "all"  (default: "all")
        page        — page number (default: 1)
        per_page    — page size (default: 20)
    """
    pred_session = PredSession()
    user = g.pred_user

    league_id = request.args.get("league_id", type=int)
    status_filter = request.args.get("status", "all")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    stmt = select(PredPick).where(PredPick.user_id == user.id)

    if league_id:
        stmt = stmt.where(PredPick.league_id == league_id)

    if status_filter == "graded":
        stmt = stmt.join(PredResult, PredPick.id == PredResult.pick_id)
    elif status_filter == "pending":
        stmt = stmt.outerjoin(PredResult, PredPick.id == PredResult.pick_id).where(
            PredResult.id.is_(None)
        )

    stmt = stmt.order_by(PredPick.game_scheduled_start.desc())

    # Count total
    all_ids = pred_session.execute(stmt.with_only_columns(PredPick.id)).scalars().all()
    total = len(all_ids)

    offset = (page - 1) * per_page
    picks = pred_session.execute(stmt.offset(offset).limit(per_page)).scalars().all()

    hb_session = HBSession()
    picks_data = [_enrich_pick(pick, hb_session) for pick in picks]

    return jsonify({
        "picks": picks_data,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    })


@picks_bp.route("/<int:pick_id>", methods=["GET"])
@require_auth
def get_pick(pick_id: int):
    """GET /api/picks/<pick_id> — single pick detail."""
    pred_session = PredSession()
    user = g.pred_user

    pick = pred_session.get(PredPick, pick_id)
    if pick is None or pick.user_id != user.id:
        return error_response("NOT_FOUND", "Pick not found", 404)

    hb_session = HBSession()
    return jsonify(_enrich_pick(pick, hb_session))


@picks_bp.route("/<int:pick_id>", methods=["DELETE"])
@require_auth
def delete_pick(pick_id: int):
    """DELETE /api/picks/<pick_id> — retract a pick."""
    pred_session = PredSession()
    user = g.pred_user

    try:
        # Get pick before retracting to know if we need to refund
        pick_to_retract = pred_session.get(PredPick, pick_id)
        effective_wager_refund = (
            pick_to_retract.effective_wager
            if pick_to_retract and pick_to_retract.effective_wager is not None
            else 0
        )
        retract_pick(user, pick_id, pred_session)
        # Refund effective wager on retraction
        if effective_wager_refund > 0:
            from app.models.pred_user import PredUser as PredUserModel
            db_user = pred_session.get(PredUserModel, user.id)
            if db_user:
                db_user.balance += effective_wager_refund
        pred_session.commit()
    except PickError as exc:
        pred_session.rollback()
        return error_response(exc.code, exc.message, exc.http_status)
    except Exception as exc:
        pred_session.rollback()
        return error_response("INTERNAL_ERROR", str(exc), 500)

    return jsonify({"message": "Pick retracted"}), 200

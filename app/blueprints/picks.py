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
from app.db import PredSession
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

picks_bp = Blueprint("picks", __name__)


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
    missing = [f for f in ("game_id", "league_id", "picked_team_id") if f not in data]
    if missing:
        return error_response(
            "VALIDATION_ERROR", f"Missing required fields: {', '.join(missing)}", 400
        )

    game_id = data["game_id"]
    league_id = data["league_id"]
    picked_team_id = data["picked_team_id"]
    confidence = data.get("confidence", 1)

    if confidence not in (1, 2, 3):
        return error_response("VALIDATION_ERROR", "Confidence must be 1, 2, or 3", 400)

    pred_session = PredSession()
    user = g.pred_user

    try:
        pick = submit_pick(
            user=user,
            game_id=game_id,
            league_id=league_id,
            picked_team_id=picked_team_id,
            confidence=confidence,
            pred_session=pred_session,
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

    return jsonify({
        "pick_id": pick.id,
        "game_id": pick.game_id,
        "league_id": pick.league_id,
        "picked_team_id": pick.picked_team_id,
        "confidence": pick.confidence,
        "is_upset_pick": pick.is_upset_pick,
        "skill_differential": (
            float(pick.skill_differential) if pick.skill_differential is not None else None
        ),
        "projected_points": projected,
        "lock_deadline": lock_deadline.isoformat() if lock_deadline else None,
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

    picks_data = []
    for pick in picks:
        pick_dict = pick.to_dict()
        if pick.result:
            pick_dict["result"] = pick.result.to_dict()
        picks_data.append(pick_dict)

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

    pick_dict = pick.to_dict()
    if pick.result:
        pick_dict["result"] = pick.result.to_dict()

    return jsonify(pick_dict)


@picks_bp.route("/<int:pick_id>", methods=["DELETE"])
@require_auth
def delete_pick(pick_id: int):
    """DELETE /api/picks/<pick_id> — retract a pick."""
    pred_session = PredSession()
    user = g.pred_user

    try:
        retract_pick(user, pick_id, pred_session)
        pred_session.commit()
    except PickError as exc:
        pred_session.rollback()
        return error_response(exc.code, exc.message, exc.http_status)
    except Exception as exc:
        pred_session.rollback()
        return error_response("INTERNAL_ERROR", str(exc), 500)

    return jsonify({"message": "Pick retracted"}), 200

"""
Identity blueprint — link a PredUser to their hockey_blast human profile.

Routes:
    GET  /api/identity/candidates  — search for matching humans in hockey_blast
    POST /api/identity/confirm     — confirm or skip identity linking
"""

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select, func, distinct

from app.auth.jwt_validator import require_auth
from app.db import HBSession, PredSession
from app.utils.response import error_response

identity_bp = Blueprint("identity", __name__)


def _get_hb_models():
    """Import hockey_blast ORM models. Returns (Human, GameRoster, Game, Organization) or raises."""
    try:
        from hockey_blast_common_lib.models import Human, GameRoster, Game, Organization
        return Human, GameRoster, Game, Organization
    except ImportError as exc:
        raise RuntimeError("hockey_blast_common_lib not available") from exc


@identity_bp.route("/candidates", methods=["GET"])
@require_auth
def get_candidates():
    """
    GET /api/identity/candidates

    Search for hockey_blast human profiles that might match the current user.

    Extracts first/last name from g.pred_user.display_name (split on first space).
    Optional query param: ?name=Pavel+Kletskov to override the search name.

    Returns:
        { "candidates": [ { id, first_name, last_name, skill_value, orgs, last_game_date } ] }
    """
    user = g.pred_user

    # Determine search name
    name_override = request.args.get("name", "").strip()
    if name_override:
        parts = name_override.split(None, 1)
    else:
        parts = (user.display_name or "").split(None, 1)

    first = parts[0] if len(parts) > 0 else ""
    last = parts[1] if len(parts) > 1 else ""

    if not first and not last:
        return jsonify({"candidates": []})

    try:
        Human, GameRoster, Game, Organization = _get_hb_models()
    except RuntimeError as exc:
        return error_response("SERVICE_UNAVAILABLE", str(exc), 503)

    hb_session = HBSession()

    try:
        # Build the query using SQLAlchemy ORM/select()
        # We need: humans who match first+last name, with their orgs and last game date
        stmt = (
            select(
                Human.id,
                Human.first_name,
                Human.last_name,
                Human.skater_skill_value,
                func.array_agg(distinct(Organization.name)).label("orgs"),
                func.max(Game.date).label("last_game_date"),
            )
            .join(GameRoster, GameRoster.human_id == Human.id)
            .join(Game, Game.id == GameRoster.game_id)
            .join(Organization, Organization.id == Game.org_id)
            .where(
                Human.first_name.ilike(f"%{first}%") if first else True,
                Human.last_name.ilike(f"%{last}%") if last else True,
            )
            .group_by(Human.id, Human.first_name, Human.last_name, Human.skater_skill_value)
            .order_by(func.max(Game.date).desc())
            .limit(10)
        )

        rows = hb_session.execute(stmt).all()

        candidates = []
        for row in rows:
            candidates.append({
                "id": row.id,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "skill_value": float(row.skater_skill_value) if row.skater_skill_value is not None else None,
                "orgs": list(row.orgs) if row.orgs else [],
                "last_game_date": row.last_game_date.isoformat() if row.last_game_date else None,
            })

        return jsonify({"candidates": candidates})

    except Exception as exc:
        return error_response("INTERNAL_ERROR", f"Query failed: {exc}", 500)


@identity_bp.route("/confirm", methods=["POST"])
@require_auth
def confirm_identity():
    """
    POST /api/identity/confirm

    Body: { "hb_human_id": 12345 }
       or { "skip": true }

    - skip: true → sets hb_human_id = -1 (declined to link)
    - hb_human_id: int → verifies the human exists, then links

    Returns: { "linked": bool, "hb_human_id": int }
    """
    user = g.pred_user
    data = request.get_json(force=True, silent=True) or {}

    pred_session = PredSession()

    if data.get("skip"):
        # Sentinel value -1 = "user declined to link"
        user.hb_human_id = -1
        pred_session.commit()
        return jsonify({"linked": False, "hb_human_id": -1})

    hb_human_id = data.get("hb_human_id")
    if hb_human_id is None:
        return error_response("VALIDATION_ERROR", "Must provide 'hb_human_id' or 'skip: true'", 400)

    if not isinstance(hb_human_id, int) or hb_human_id <= 0:
        return error_response("VALIDATION_ERROR", "hb_human_id must be a positive integer", 400)

    # Verify the human exists in hockey_blast DB
    try:
        Human, _, _, _ = _get_hb_models()
        hb_session = HBSession()
        human = hb_session.get(Human, hb_human_id)
        if human is None:
            return error_response("NOT_FOUND", f"No human found with id={hb_human_id}", 404)
    except RuntimeError as exc:
        return error_response("SERVICE_UNAVAILABLE", str(exc), 503)

    user.hb_human_id = hb_human_id
    pred_session.commit()

    return jsonify({"linked": True, "hb_human_id": hb_human_id})

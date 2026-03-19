"""
Admin blueprint — manage claims and users.

Routes (all require is_admin):
    GET  /api/admin/claims                     — list claims (filter by status)
    GET  /api/admin/claims/<id>                — claim detail
    POST /api/admin/claims/<id>/approve        — approve a claim
    POST /api/admin/claims/<id>/reject         — reject a claim
    GET  /api/admin/users                      — list all users
    POST /api/admin/users/<id>/toggle-admin    — toggle is_admin (super admin only)
"""

from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select, func

from app.auth.admin_required import require_admin
from app.db import PredSession
from app.models.pred_user import PredUser
from app.models.pred_user_hb_claim import PredUserHbClaim
from app.utils.response import error_response

# Super admin — only this user can grant/revoke admin on others
SUPER_ADMIN_ID = 17

admin_bp = Blueprint("admin", __name__)


# ── Helper ──────────────────────────────────────────────────────────────────

def _claim_detail(claim: PredUserHbClaim, pred_session) -> dict:
    """Enrich a claim dict with the claimant's display info."""
    d = claim.to_dict()
    user = pred_session.get(PredUser, claim.user_id)
    d["user_display_name"] = user.display_name if user else None
    d["user_email"] = user.email if user else None
    return d


# ── Claims ──────────────────────────────────────────────────────────────────

@admin_bp.route("/claims", methods=["GET"])
@require_admin
def list_claims():
    """
    GET /api/admin/claims[?status=pending_review|confirmed|rejected|all]

    Default: returns all claims. Filter with ?status=...
    """
    status = request.args.get("status", "all")
    pred_session = PredSession()

    q = select(PredUserHbClaim)
    if status != "all":
        q = q.where(PredUserHbClaim.claim_status == status)
    q = q.order_by(PredUserHbClaim.claimed_at.desc())

    claims = pred_session.execute(q).scalars().all()
    return jsonify({
        "claims": [_claim_detail(c, pred_session) for c in claims],
        "count": len(claims),
        "status_filter": status,
    })


@admin_bp.route("/claims/<int:claim_id>", methods=["GET"])
@require_admin
def get_claim(claim_id: int):
    """GET /api/admin/claims/<id> — claim detail."""
    pred_session = PredSession()
    claim = pred_session.get(PredUserHbClaim, claim_id)
    if claim is None:
        return error_response("NOT_FOUND", f"No claim with id={claim_id}", 404)
    return jsonify(_claim_detail(claim, pred_session))


@admin_bp.route("/claims/<int:claim_id>/approve", methods=["POST"])
@require_admin
def approve_claim(claim_id: int):
    """
    POST /api/admin/claims/<id>/approve
    Body (optional): { "note": "..." }

    Sets claim_status = 'confirmed'. Also links user.hb_human_id if they don't
    have a primary claim yet.
    """
    pred_session = PredSession()
    claim = pred_session.get(PredUserHbClaim, claim_id)
    if claim is None:
        return error_response("NOT_FOUND", f"No claim with id={claim_id}", 404)

    data = request.get_json(force=True, silent=True) or {}
    note = data.get("note") or None

    claim.claim_status = "confirmed"
    claim.admin_note = note
    claim.reviewed_by = g.pred_user.id
    claim.reviewed_at = datetime.now(timezone.utc)

    # Link hb_human_id on user if they don't have one yet
    claimant = pred_session.get(PredUser, claim.user_id)
    if claimant and claimant.hb_human_id is None:
        claimant.hb_human_id = claim.hb_human_id
        claim.is_primary = True

    pred_session.commit()
    return jsonify({"ok": True, "claim": _claim_detail(claim, pred_session)})


@admin_bp.route("/claims/<int:claim_id>/reject", methods=["POST"])
@require_admin
def reject_claim(claim_id: int):
    """
    POST /api/admin/claims/<id>/reject
    Body (optional): { "note": "..." }

    Sets claim_status = 'rejected'.
    """
    pred_session = PredSession()
    claim = pred_session.get(PredUserHbClaim, claim_id)
    if claim is None:
        return error_response("NOT_FOUND", f"No claim with id={claim_id}", 404)

    data = request.get_json(force=True, silent=True) or {}
    note = data.get("note") or None

    claim.claim_status = "rejected"
    claim.admin_note = note
    claim.reviewed_by = g.pred_user.id
    claim.reviewed_at = datetime.now(timezone.utc)

    pred_session.commit()
    return jsonify({"ok": True, "claim": _claim_detail(claim, pred_session)})


# ── Users ────────────────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@require_admin
def list_users():
    """GET /api/admin/users — all users with claim counts."""
    pred_session = PredSession()

    # Subquery: claim count per user
    claim_counts = pred_session.execute(
        select(
            PredUserHbClaim.user_id,
            func.count(PredUserHbClaim.id).label("claim_count"),
        ).group_by(PredUserHbClaim.user_id)
    ).all()
    count_map = {r.user_id: r.claim_count for r in claim_counts}

    users = pred_session.execute(
        select(PredUser).order_by(PredUser.created_at.desc())
    ).scalars().all()

    return jsonify({
        "users": [
            {
                **u.to_dict(),
                "claim_count": count_map.get(u.id, 0),
            }
            for u in users
        ],
        "count": len(users),
    })


@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@require_admin
def toggle_admin(user_id: int):
    """
    POST /api/admin/users/<id>/toggle-admin

    Toggles is_admin on a user. Only the super admin (id=17) can do this.
    """
    if g.pred_user.id != SUPER_ADMIN_ID:
        return jsonify({"error": "FORBIDDEN", "message": "Only super admin can grant/revoke admin"}), 403

    pred_session = PredSession()
    target = pred_session.get(PredUser, user_id)
    if target is None:
        return error_response("NOT_FOUND", f"No user with id={user_id}", 404)

    # Prevent removing super admin's own admin status
    if target.id == SUPER_ADMIN_ID:
        return jsonify({"error": "FORBIDDEN", "message": "Cannot change super admin status"}), 403

    target.is_admin = not target.is_admin
    pred_session.commit()
    return jsonify({"ok": True, "user_id": user_id, "is_admin": target.is_admin})


# ── Fantasy Season Launch ──────────────────────────────────────────────────

@admin_bp.route("/fantasy/active-levels", methods=["GET"])
@require_admin
def get_active_levels():
    """
    GET /api/admin/fantasy/active-levels?org_id=1&active_only=true
    Returns levels that have recent/active season dates.
    active_only=true (default): end_date >= today - 30 days
    """
    from datetime import date, timedelta
    from sqlalchemy import select, distinct as sa_distinct
    from hockey_blast_common_lib.models import OrgLeagueSeasonDates, Division, Level
    from app.db import HBSession

    org_id = request.args.get("org_id", 1, type=int)
    active_only = request.args.get("active_only", "true").lower() != "false"

    hb = HBSession()

    stmt = (
        select(Division.level_id, Level.level_name, Level.short_name)
        .join(
            OrgLeagueSeasonDates,
            (OrgLeagueSeasonDates.league_number == Division.league_number) &
            (OrgLeagueSeasonDates.season_number == Division.season_number) &
            (OrgLeagueSeasonDates.org_id == Division.org_id),
        )
        .join(Level, Level.id == Division.level_id)
        .where(Division.org_id == org_id)
        .distinct()
    )

    if active_only:
        cutoff = date.today() - timedelta(days=30)
        stmt = stmt.where(OrgLeagueSeasonDates.end_date >= cutoff)

    rows = hb.execute(stmt).all()

    # Deduplicate by level_id and sort by level_name
    seen = {}
    for row in rows:
        if row.level_id not in seen:
            seen[row.level_id] = {
                "level_id": row.level_id,
                "level_name": row.level_name,
                "short_name": row.short_name,
            }

    levels = sorted(seen.values(), key=lambda x: x["level_name"] or "")
    return jsonify({"levels": levels})


@admin_bp.route("/fantasy/launch-season", methods=["POST"])
@require_admin
def launch_fantasy_season():
    """
    POST /api/admin/fantasy/launch-season
    Body: { org_id, level_ids: [], season_start_date: "YYYY-MM-DD" }
    Sets season_started_at on matching fantasy leagues and marks them active.
    """
    from datetime import date
    from sqlalchemy import select
    from app.models.fantasy_league import FantasyLeague
    from app.db import PredSession

    data = request.get_json(silent=True) or {}
    org_id = data.get("org_id", 1)
    level_ids = data.get("level_ids", [])
    season_start_date = data.get("season_start_date")

    if not level_ids:
        return jsonify({"error": "VALIDATION_ERROR", "message": "level_ids required"}), 400
    if not season_start_date:
        return jsonify({"error": "VALIDATION_ERROR", "message": "season_start_date required"}), 400

    try:
        from datetime import datetime
        start_dt = datetime.strptime(season_start_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "VALIDATION_ERROR", "message": "season_start_date must be YYYY-MM-DD"}), 400

    pred = PredSession()
    stmt = select(FantasyLeague).where(
        FantasyLeague.org_id == org_id,
        FantasyLeague.level_id.in_(level_ids),
        FantasyLeague.status.in_(["forming", "active"]),
    )
    leagues = pred.execute(stmt).scalars().all()

    updated = []
    for league in leagues:
        league.season_started_at = start_dt
        if league.status == "forming":
            league.status = "active"
        updated.append({"id": league.id, "name": league.name, "status": league.status})

    pred.commit()
    return jsonify({"updated": updated, "count": len(updated)})

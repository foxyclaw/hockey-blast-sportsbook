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
import sqlalchemy as sa
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
    """Enrich a claim dict with the claimant's display info and conflict info."""
    d = claim.to_dict()
    user = pred_session.get(PredUser, claim.user_id)
    d["user_display_name"] = user.display_name if user else None
    d["user_email"] = user.email if user else None

    # For pending_review claims, show context for admin decision
    if claim.claim_status == "pending_review":
        snapshot = claim.profile_snapshot or {}
        claimed_name = f"{snapshot.get('first_name', '')} {snapshot.get('last_name', '')}".strip()

        conflicting = pred_session.execute(
            select(PredUserHbClaim).where(
                PredUserHbClaim.hb_human_id == claim.hb_human_id,
                PredUserHbClaim.user_id != claim.user_id,
                PredUserHbClaim.claim_status == "confirmed",
            )
        ).scalars().first()
        existing_user = pred_session.get(PredUser, conflicting.user_id) if conflicting else None

        d["review_context"] = {
            "login_name": user.display_name if user else None,
            "claimed_name": claimed_name,
            "is_manual_search": claim.source == "manual_search",
            "conflict_with": {
                "user_display_name": existing_user.display_name if existing_user else None,
                "user_email": existing_user.email if existing_user else None,
            } if conflicting else None,
        }

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

    claimant = pred_session.get(PredUser, claim.user_id)

    # If this was the user's primary claim, clear hb_human_id from the user record
    if claim.is_primary and claimant and claimant.hb_human_id == claim.hb_human_id:
        claimant.hb_human_id = None
        # Promote another confirmed claim to primary if one exists
        other = pred_session.execute(
            select(PredUserHbClaim).where(
                PredUserHbClaim.user_id == claim.user_id,
                PredUserHbClaim.id != claim.id,
                PredUserHbClaim.claim_status == "confirmed",
            )
        ).scalars().first()
        if other:
            other.is_primary = True
            claimant.hb_human_id = other.hb_human_id

    # Delete the claim entirely — no trace left
    pred_session.delete(claim)
    pred_session.commit()
    return jsonify({"ok": True, "deleted": True})


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
    Returns levels that have active seasons.
    Uses Season table (kept up to date) joined to Division → Level.
    active_only=true (default): Season.end_date >= today - 30 days
    """
    from datetime import date, timedelta
    from sqlalchemy import select
    from hockey_blast_common_lib.models import Season, Division, Level
    from app.db import HBSession

    org_id = request.args.get("org_id", 1, type=int)
    active_only = request.args.get("active_only", "true").lower() != "false"

    hb = HBSession()

    stmt = (
        select(Division.level_id, Level.level_name, Level.short_name)
        .join(Season, Season.id == Division.season_id)
        .join(Level, Level.id == Division.level_id)
        .where(Season.org_id == org_id)
        .distinct()
    )

    if active_only:
        cutoff = date.today() - timedelta(days=30)
        stmt = stmt.where(Season.end_date >= cutoff)

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

    import re

    def _natural_sort_key(x):
        name = x["short_name"] or x["level_name"] or ""
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', name)]

    # Filter out levels with no display name
    levels = sorted(
        [v for v in seen.values() if v["short_name"] or v["level_name"]],
        key=_natural_sort_key,
    )
    return jsonify({"levels": levels})


@admin_bp.route("/fantasy/orgs", methods=["GET"])
@require_admin
def get_fantasy_orgs():
    """GET /api/admin/fantasy/orgs — list all orgs for the org selector."""
    from sqlalchemy import select
    from hockey_blast_common_lib.models import Organization
    from app.db import HBSession

    hb = HBSession()
    orgs = hb.execute(
        select(Organization.id, Organization.organization_name)
        .where(Organization.id > 0)
        .order_by(Organization.id)
    ).all()

    return jsonify({"orgs": [{"id": o.id, "name": o.organization_name} for o in orgs]})


@admin_bp.route("/fantasy/launch-season", methods=["POST"])
@require_admin
def launch_fantasy_season():
    """
    POST /api/admin/fantasy/launch-season
    Body: { org_id, level_ids: [], season_start_date: "YYYY-MM-DD" }
    Sets season_starts_at on matching fantasy leagues and marks them active.
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

    from hockey_blast_common_lib.models import Level
    from app.db import HBSession, PredSession
    from app.models.fantasy_league import FantasyLeague
    from app.services.fantasy_pool_service import get_player_pool

    hb = HBSession()
    pred = PredSession()

    created = []
    updated = []

    for level_id in level_ids:
        # Get level name
        level = hb.get(Level, level_id)
        level_name = level.level_name if level else str(level_id)

        # Check if league already exists for this level/org
        existing = pred.execute(
            select(FantasyLeague).where(
                FantasyLeague.org_id == org_id,
                FantasyLeague.level_id == level_id,
                FantasyLeague.status.in_(["forming", "active", "drafting", "draft_open"]),
            )
        ).scalar_one_or_none()

        if existing:
            # Update existing league
            existing.season_starts_at = start_dt
            if existing.status == "forming":
                existing.status = "active"
            updated.append({"id": existing.id, "name": existing.name, "action": "updated"})
        else:
            # Create new league — get pool info for sizing
            try:
                pool = get_player_pool(level_id, org_id)
                max_managers = pool.get("max_managers", 8)
                roster_skaters = pool.get("roster_skaters", 6)
            except Exception:
                max_managers = 8
                roster_skaters = 6

            display_level = level.short_name or level_name if level else str(level_id)
            league_name = f"Level {display_level} — Spring 2026"
            new_league = FantasyLeague(
                name=league_name,
                level_id=level_id,
                level_name=level_name,
                org_id=org_id,
                season_label="Spring 2026",
                status="active",
                max_managers=max_managers,
                roster_skaters=roster_skaters,
                roster_goalies=1,
                draft_pick_hours=24,
                season_starts_at=start_dt,
            )
            pred.add(new_league)
            pred.flush()
            created.append({"id": new_league.id, "name": new_league.name, "action": "created"})

    pred.commit()
    all_results = created + updated
    return jsonify({
        "created": len(created),
        "updated": len(updated),
        "count": len(all_results),
        "leagues": all_results,
    })


@admin_bp.route("/fantasy/leagues", methods=["GET"])
@require_admin
def list_fantasy_leagues():
    """GET /api/admin/fantasy/leagues?org_id=1 — list all leagues for an org."""
    from sqlalchemy import select
    from app.models.fantasy_league import FantasyLeague
    from app.db import PredSession

    org_id = request.args.get("org_id", 1, type=int)
    pred = PredSession()
    leagues = pred.execute(
        select(FantasyLeague)
        .where(FantasyLeague.org_id == org_id)
        .order_by(
            sa.case(
                {"active": 0, "drafting": 1, "draft_open": 2, "forming": 3, "completed": 4},
                value=FantasyLeague.status,
                else_=5,
            ).asc(),
            FantasyLeague.name.asc(),
        )
    ).scalars().all()

    return jsonify({"leagues": [l.to_dict() for l in leagues]})


@admin_bp.route("/fantasy/leagues/<int:league_id>", methods=["DELETE"])
@require_admin
def delete_fantasy_league(league_id: int):
    """DELETE /api/admin/fantasy/leagues/<id> — delete a league and all related data."""
    from sqlalchemy import select, delete as sa_delete
    from app.models.fantasy_league import FantasyLeague
    from app.models.fantasy_manager import FantasyManager
    from app.models.fantasy_roster import FantasyRoster
    from app.models.fantasy_draft_queue import FantasyDraftQueue
    from app.models.fantasy_standings import FantasyStandings
    from app.db import PredSession

    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if not league:
        return jsonify({"error": "NOT_FOUND", "message": "League not found"}), 404

    name = league.name

    # Delete all related data in order
    pred.execute(sa_delete(FantasyStandings).where(FantasyStandings.league_id == league_id))
    pred.execute(sa_delete(FantasyDraftQueue).where(FantasyDraftQueue.league_id == league_id))
    pred.execute(sa_delete(FantasyRoster).where(FantasyRoster.league_id == league_id))
    pred.execute(sa_delete(FantasyManager).where(FantasyManager.league_id == league_id))
    pred.delete(league)
    pred.commit()

    return jsonify({"ok": True, "deleted": name})


@admin_bp.route("/fantasy/leagues/batch-delete", methods=["POST"])
@require_admin
def batch_delete_fantasy_leagues():
    """POST /api/admin/fantasy/leagues/batch-delete — delete multiple leagues and all their data."""
    from sqlalchemy import delete as sa_delete
    from app.models.fantasy_league import FantasyLeague
    from app.models.fantasy_manager import FantasyManager
    from app.models.fantasy_roster import FantasyRoster
    from app.models.fantasy_draft_queue import FantasyDraftQueue
    from app.models.fantasy_standings import FantasyStandings
    from app.db import PredSession

    data = request.get_json(silent=True) or {}
    league_ids = data.get("league_ids", [])
    if not league_ids:
        return jsonify({"error": "VALIDATION_ERROR", "message": "league_ids required"}), 400

    pred = PredSession()
    leagues = pred.execute(select(FantasyLeague).where(FantasyLeague.id.in_(league_ids))).scalars().all()
    names = [l.name for l in leagues]

    pred.execute(sa_delete(FantasyStandings).where(FantasyStandings.league_id.in_(league_ids)))
    pred.execute(sa_delete(FantasyDraftQueue).where(FantasyDraftQueue.league_id.in_(league_ids)))
    pred.execute(sa_delete(FantasyRoster).where(FantasyRoster.league_id.in_(league_ids)))
    pred.execute(sa_delete(FantasyManager).where(FantasyManager.league_id.in_(league_ids)))
    pred.execute(sa_delete(FantasyLeague).where(FantasyLeague.id.in_(league_ids)))
    pred.commit()

    return jsonify({"ok": True, "deleted": len(names), "names": names})

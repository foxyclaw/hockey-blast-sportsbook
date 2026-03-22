"""
Admin blueprint — manage claims and users.

Routes (all require is_admin):
    GET  /api/admin/claims                     — list claims (filter by status)
    GET  /api/admin/claims/<id>                — claim detail
    POST /api/admin/claims/<id>/approve        — approve a single claim
    POST /api/admin/claims/<id>/reject         — reject a claim
    POST /api/admin/claims/approve-batch       — approve ALL pending claims for a user at once
    GET  /api/admin/users                      — list all users
    POST /api/admin/users/<id>/toggle-admin    — toggle is_admin (super admin only)
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
import sqlalchemy as sa
from sqlalchemy import select, func

from hockey_blast_common_lib.merge_humans import merge_humans

from app.auth.admin_required import require_admin
from app.db import HBSession, PredSession
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

    # If the user now has 2+ confirmed claims, merge all secondary human IDs
    # into the primary one in the hockey_blast DB.
    try:
        confirmed_claims = pred_session.execute(
            select(PredUserHbClaim).where(
                PredUserHbClaim.user_id == claim.user_id,
                PredUserHbClaim.claim_status == "confirmed",
            )
        ).scalars().all()

        if len(confirmed_claims) >= 2:
            primary_claim = next((c for c in confirmed_claims if c.is_primary), None)
            if primary_claim:
                import os as _os
                from sqlalchemy import create_engine as _create_engine
                from sqlalchemy.orm import sessionmaker as _sessionmaker
                _boss_url = _os.environ.get("HB_BOSS_DATABASE_URL")
                if _boss_url:
                    _boss_engine = _create_engine(_boss_url)
                    hb_session = _sessionmaker(bind=_boss_engine)()
                else:
                    hb_session = HBSession()
                merged_secondary_claims = []
                for secondary_claim in confirmed_claims:
                    if secondary_claim.id != primary_claim.id:
                        merge_humans(
                            hb_session,
                            primary_human_id=primary_claim.hb_human_id,
                            secondary_human_id=secondary_claim.hb_human_id,
                        )
                        merged_secondary_claims.append(secondary_claim)
                hb_session.close()
                now_utc = datetime.now(timezone.utc)
                for sc in merged_secondary_claims:
                    sc.merged_at = now_utc
                pred_session.commit()
    except Exception:
        logging.getLogger(__name__).exception(
            "merge_humans failed for user_id=%d after approving claim_id=%d",
            claim.user_id,
            claim_id,
        )

    return jsonify({"ok": True, "claim": _claim_detail(claim, pred_session)})


@admin_bp.route("/claims/approve-batch", methods=["POST"])
@require_admin
def approve_claims_batch():
    """
    POST /api/admin/claims/approve-batch
    Body: { "user_id": 43, "note": "..." }

    Approves ALL pending_review claims for a user in one shot, then fires merge.
    This is the preferred flow — avoids ambiguity from approving claims one-by-one.

    Primary assignment (when user has no hb_human_id yet):
    - Prefer a pending claim already marked is_primary.
    - Fall back to the first pending claim in the list.
    """
    pred_session = PredSession()
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    note = data.get("note") or None

    if not isinstance(user_id, int) or user_id <= 0:
        return error_response("VALIDATION_ERROR", "user_id must be a positive integer", 400)

    claimant = pred_session.get(PredUser, user_id)
    if claimant is None:
        return error_response("NOT_FOUND", f"No user with id={user_id}", 404)

    pending = pred_session.execute(
        select(PredUserHbClaim).where(
            PredUserHbClaim.user_id == user_id,
            PredUserHbClaim.claim_status == "pending_review",
        )
    ).scalars().all()

    if not pending:
        return jsonify({"ok": True, "approved_count": 0, "claims": [], "message": "No pending claims for this user"})

    now_utc = datetime.now(timezone.utc)

    for claim in pending:
        claim.claim_status = "confirmed"
        claim.admin_note = note
        claim.reviewed_by = g.pred_user.id
        claim.reviewed_at = now_utc

    # Link hb_human_id if not set yet — pick the designated primary,
    # or fall back to the HB human with the latest last_date (most recently active).
    if claimant.hb_human_id is None:
        explicit_primary = next((c for c in pending if c.is_primary), None)
        if explicit_primary:
            primary_claim = explicit_primary
        else:
            # Pick the most recently active human in HB
            try:
                from hockey_blast_common_lib.models import Human as _Human
                _hb = HBSession()
                best_claim = pending[0]
                best_date = None
                for c in pending:
                    h = _hb.get(_Human, c.hb_human_id)
                    if h and h.last_date and (best_date is None or h.last_date > best_date):
                        best_date = h.last_date
                        best_claim = c
                primary_claim = best_claim
            except Exception:
                primary_claim = pending[0]
        primary_claim.is_primary = True
        claimant.hb_human_id = primary_claim.hb_human_id

    pred_session.commit()

    # Fire merge across all confirmed claims
    try:
        confirmed_claims = pred_session.execute(
            select(PredUserHbClaim).where(
                PredUserHbClaim.user_id == user_id,
                PredUserHbClaim.claim_status == "confirmed",
            )
        ).scalars().all()

        if len(confirmed_claims) >= 2:
            primary_claim = next((c for c in confirmed_claims if c.is_primary), None)
            if primary_claim:
                import os as _os
                from sqlalchemy import create_engine as _create_engine
                from sqlalchemy.orm import sessionmaker as _sessionmaker
                _boss_url = _os.environ.get("HB_BOSS_DATABASE_URL")
                hb_session = _sessionmaker(bind=_create_engine(_boss_url))() if _boss_url else HBSession()
                merged_secondary_claims = []
                for secondary_claim in confirmed_claims:
                    if secondary_claim.id != primary_claim.id and not secondary_claim.merged_at:
                        try:
                            merge_humans(hb_session, primary_claim.hb_human_id, secondary_claim.hb_human_id)
                            merged_secondary_claims.append(secondary_claim)
                        except Exception:
                            logging.getLogger(__name__).exception(
                                "merge_humans failed for hb_human_id=%d", secondary_claim.hb_human_id
                            )
                hb_session.close()
                for sc in merged_secondary_claims:
                    sc.merged_at = now_utc
                pred_session.commit()
    except Exception:
        logging.getLogger(__name__).exception(
            "batch merge failed for user_id=%d", user_id
        )

    all_claims = pred_session.execute(
        select(PredUserHbClaim).where(PredUserHbClaim.user_id == user_id)
    ).scalars().all()

    return jsonify({
        "ok": True,
        "approved_count": len(pending),
        "claims": [_claim_detail(c, pred_session) for c in all_claims],
    })


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


@admin_bp.route("/chat/questions", methods=["GET"])
@require_admin
def chat_questions():
    """GET /api/admin/chat/questions — recent chat queries, no answers."""
    from app.models.chat_message import ChatMessage
    from app.models.pred_user import PredUser

    limit = min(int(request.args.get("limit", 100)), 500)
    pred_session = PredSession()

    messages = pred_session.execute(
        select(ChatMessage)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).scalars().all()

    result = []
    user_cache = {}
    for m in messages:
        if m.user_id not in user_cache:
            u = pred_session.get(PredUser, m.user_id)
            user_cache[m.user_id] = u.display_name if u else f"user#{m.user_id}"
        result.append({
            "id": m.id,
            "user": user_cache[m.user_id],
            "query": m.query,
            "is_off_topic": m.is_off_topic,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    return jsonify({"questions": result, "count": len(result)})


def _build_orgs_list(org_ids) -> list:
    """Build orgs dropdown list from a list of org_ids, fetching names from HB."""
    orgs_out = [{"id": None, "name": "All Orgs"}]
    present_org_ids = {oid for oid in org_ids if oid is not None}
    if present_org_ids:
        try:
            from hockey_blast_common_lib.models import Organization
            hb = HBSession()
            org_objs = hb.execute(
                select(Organization.id, Organization.organization_name)
                .where(Organization.id.in_(present_org_ids))
                .order_by(Organization.id)
            ).all()
            orgs_out += [{"id": o.id, "name": o.organization_name} for o in org_objs]
        except Exception as e:
            logging.getLogger(__name__).warning("Could not fetch org names: %s", e)
            orgs_out += [{"id": oid, "name": f"Org #{oid}"} for oid in sorted(present_org_ids)]
    return orgs_out


@admin_bp.route("/prediction-analysis", methods=["GET"])
@require_admin
def prediction_analysis():
    """
    GET /api/admin/prediction-analysis

    Measures system prediction accuracy using the game_prediction_logs table.
    Logs are snapshotted at first-pick time and compared against final HB scores.

    Key rule: lower avg_skill = better team (0=elite, 100=worst).
    Predicted winner = team with lower avg_skill (stored in game_prediction_logs).

    Query params:
        min_skill_diff (float, default 0.0) — exclude games where abs(skill_differential) < threshold
        org_id (int, optional) — filter by org_id from game_prediction_logs

    Response:
        weeks[]   — weekly accuracy (newest first)
        overall   — aggregate stats + by_skill_diff_bucket breakdown
        orgs[]    — [{id, name}] available orgs
    """
    from datetime import date, timedelta
    from collections import defaultdict

    from app.models.game_prediction_log import GamePredictionLog

    FINAL_STATUSES = {"Final", "Final.", "Final/OT", "Final/OT2", "Final/SO", "Final(SO)"}

    min_skill_diff = request.args.get("min_skill_diff", 0.0, type=float)
    org_id_filter = request.args.get("org_id", None, type=int)

    pred_session = PredSession()

    # ── 1. Query game_prediction_logs ─────────────────────────────────────────
    stmt = select(GamePredictionLog).where(
        func.abs(GamePredictionLog.skill_differential) >= min_skill_diff
    )
    if org_id_filter is not None:
        stmt = stmt.where(GamePredictionLog.org_id == org_id_filter)

    log_rows = pred_session.execute(stmt).scalars().all()

    # Build orgs list from all logs (unfiltered) for the dropdown
    all_org_ids = pred_session.execute(
        select(GamePredictionLog.org_id).distinct()
    ).scalars().all()
    orgs_out = _build_orgs_list(all_org_ids)

    if not log_rows:
        return jsonify({
            "weeks": [],
            "overall": {
                "total": 0, "correct": 0, "rate": 0.0,
                "by_skill_diff_bucket": {
                    "0-5": {"total": 0, "correct": 0, "rate": 0.0},
                    "5-10": {"total": 0, "correct": 0, "rate": 0.0},
                    "10-20": {"total": 0, "correct": 0, "rate": 0.0},
                    "20+": {"total": 0, "correct": 0, "rate": 0.0},
                },
            },
            "orgs": orgs_out,
        })

    # ── 2. Fetch HB game results ───────────────────────────────────────────────
    game_ids = [r.game_id for r in log_rows]
    game_results: dict = {}  # game_id -> {home_final_score, visitor_final_score, status}

    try:
        from hockey_blast_common_lib.models import Game
        hb = HBSession()
        hb_games = hb.execute(
            select(
                Game.id,
                Game.home_final_score,
                Game.visitor_final_score,
                Game.status,
            ).where(Game.id.in_(game_ids))
        ).all()
        for g in hb_games:
            game_results[g.id] = {
                "home_final_score": g.home_final_score,
                "visitor_final_score": g.visitor_final_score,
                "status": g.status,
            }
    except Exception as e:
        logging.getLogger(__name__).warning("Could not fetch HB game results: %s", e)

    # ── 3. Helper functions ───────────────────────────────────────────────────
    def _rate(correct, total):
        return round(correct / total * 100, 1) if total else 0.0

    def _avg(vals):
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    def _skill_diff_bucket(diff: float) -> str:
        d = abs(diff)
        if d < 5:
            return "0-5"
        if d < 10:
            return "5-10"
        if d < 20:
            return "10-20"
        return "20+"

    # ── 4. Process each log row ───────────────────────────────────────────────
    weeks: dict = defaultdict(lambda: {
        "total": 0, "correct": 0, "skill_diffs": [],
        "upsets_total": 0, "upsets_correct": 0,
    })
    bucket_order = ["0-5", "5-10", "10-20", "20+"]
    diff_buckets: dict = defaultdict(lambda: {"total": 0, "correct": 0})

    total_games = 0
    total_correct = 0
    all_skill_diffs = []

    for log in log_rows:
        game_res = game_results.get(log.game_id)
        if game_res is None:
            continue
        if game_res["status"] not in FINAL_STATUSES:
            continue
        if game_res["home_final_score"] is None or game_res["visitor_final_score"] is None:
            continue
        if log.predicted_winner_team_id is None:
            continue

        # Determine actual winner
        if game_res["home_final_score"] > game_res["visitor_final_score"]:
            actual_winner_team_id = log.home_team_id
        else:
            actual_winner_team_id = log.away_team_id

        is_correct = (actual_winner_team_id == log.predicted_winner_team_id)
        skill_diff = float(log.skill_differential) if log.skill_differential is not None else 0.0
        abs_diff = abs(skill_diff)

        # Upset = underdog (higher skill = worse team) actually won
        is_upset = not is_correct

        total_games += 1
        if is_correct:
            total_correct += 1
        all_skill_diffs.append(abs_diff)

        # Week bucket (ISO week, Monday start)
        if log.game_scheduled_start:
            gd = (
                log.game_scheduled_start.date()
                if hasattr(log.game_scheduled_start, "date")
                else date.fromisoformat(str(log.game_scheduled_start)[:10])
            )
        elif log.game_date:
            gd = log.game_date
        else:
            gd = date(2000, 1, 1)

        week_start = gd - timedelta(days=gd.weekday())
        wk = weeks[str(week_start)]
        wk["total"] += 1
        if is_correct:
            wk["correct"] += 1
        wk["skill_diffs"].append(abs_diff)
        if is_upset:
            wk["upsets_total"] += 1
            wk["upsets_correct"] += 1

        # Skill diff bucket
        bucket = _skill_diff_bucket(skill_diff)
        diff_buckets[bucket]["total"] += 1
        if is_correct:
            diff_buckets[bucket]["correct"] += 1

    # ── 5. Format weeks output (newest first) ────────────────────────────────
    weeks_out = []
    for week_start_str in sorted(weeks.keys(), reverse=True):
        wk = weeks[week_start_str]
        weeks_out.append({
            "week_start": week_start_str,
            "total": wk["total"],
            "correct": wk["correct"],
            "rate": _rate(wk["correct"], wk["total"]),
            "avg_skill_diff": _avg(wk["skill_diffs"]),
            "upsets_correct": wk["upsets_correct"],
            "upsets_total": wk["upsets_total"],
        })

    # ── 6. By-skill-diff-bucket breakdown ────────────────────────────────────
    by_skill_diff_bucket = {}
    for bk in bucket_order:
        bdata = diff_buckets.get(bk, {"total": 0, "correct": 0})
        by_skill_diff_bucket[bk] = {
            "total": bdata["total"],
            "correct": bdata["correct"],
            "rate": _rate(bdata["correct"], bdata["total"]),
        }

    return jsonify({
        "weeks": weeks_out,
        "overall": {
            "total": total_games,
            "correct": total_correct,
            "rate": _rate(total_correct, total_games),
            "by_skill_diff_bucket": by_skill_diff_bucket,
        },
        "orgs": orgs_out,
    })


@admin_bp.route("/analytics", methods=["GET"])
@require_admin
def analytics():
    """GET /api/admin/analytics — daily event counts for the last 30 days."""
    from app.models.site_event import SiteEvent
    from sqlalchemy import func, cast, Date

    days = int(request.args.get("days", 30))
    pred_session = PredSession()

    rows = pred_session.execute(
        select(
            cast(SiteEvent.created_at, Date).label("day"),
            SiteEvent.event_type,
            func.count(SiteEvent.id).label("count"),
            func.count(func.distinct(SiteEvent.ip_address)).label("unique_ips"),
        )
        .where(SiteEvent.created_at >= sa.func.now() - sa.text(f"interval '{days} days'"))
        .group_by("day", SiteEvent.event_type)
        .order_by("day")
    ).all()

    # Pivot into {day: {visit: n, pick: n, chat: n, unique_users: n}}
    data: dict = {}
    for row in rows:
        day = str(row.day)
        if day not in data:
            data[day] = {"visit": 0, "pick": 0, "chat": 0}
        data[day][row.event_type] = row.count

    return jsonify({"days": days, "data": data})

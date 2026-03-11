"""
Identity blueprint — link a PredUser to their hockey_blast human profile.

Routes:
    GET  /api/identity/candidates  — search for matching humans in hockey_blast
    POST /api/identity/confirm     — claim one or more human IDs (append-only)
"""

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select, func, distinct

from app.auth.jwt_validator import require_auth
from app.db import HBSession, PredSession
from app.utils.response import error_response

identity_bp = Blueprint("identity", __name__)


def _get_hb_models():
    try:
        from hockey_blast_common_lib.models import (
            Human, HumanAlias, GameRoster, Game, Organization, PlayerRole, Team
        )
        return Human, HumanAlias, GameRoster, Game, Organization, PlayerRole, Team
    except ImportError as exc:
        raise RuntimeError("hockey_blast_common_lib not available") from exc


def _build_human_profile(hb_session, human_id: int) -> dict:
    """
    Build a rich profile snapshot for a human ID.
    Used both for candidate display and for saving a disaster-recovery snapshot.

    Returns a dict with: id, names (including aliases), career dates,
    skill_value, teams (with orgs and date ranges).
    """
    Human, HumanAlias, GameRoster, Game, Organization, PlayerRole, Team = _get_hb_models()

    human = hb_session.get(Human, human_id)
    if human is None:
        return {}

    # ── Name aliases (all names this person has played under) ────────────────
    alias_rows = hb_session.execute(
        select(HumanAlias).where(HumanAlias.human_id == human_id)
    ).scalars().all()

    aliases = [
        {
            "first_name": a.first_name,
            "middle_name": a.middle_name or "",
            "last_name": a.last_name,
            "suffix": a.suffix or "",
            "first_date": a.first_date.isoformat() if a.first_date else None,
            "last_date": a.last_date.isoformat() if a.last_date else None,
        }
        for a in alias_rows
    ]

    # ── Teams via player_roles (team + role + date range) ────────────────────
    team_rows = hb_session.execute(
        select(
            PlayerRole.team_id,
            PlayerRole.role_type,
            PlayerRole.first_date,
            PlayerRole.last_date,
            Team.name.label("team_name"),
            Team.org_id,
            Organization.organization_name.label("org_name"),
        )
        .join(Team, Team.id == PlayerRole.team_id)
        .join(Organization, Organization.id == Team.org_id)
        .where(PlayerRole.human_id == human_id)
        .order_by(PlayerRole.last_date.desc().nullslast())
    ).all()

    teams = [
        {
            "team_id": r.team_id,
            "team_name": r.team_name,
            "org_id": r.org_id,
            "org_name": r.org_name,
            "role_type": r.role_type,
            "first_date": r.first_date.isoformat() if r.first_date else None,
            "last_date": r.last_date.isoformat() if r.last_date else None,
        }
        for r in team_rows
    ]

    # Unique orgs (for quick display)
    orgs = list({r["org_name"] for r in teams if r["org_name"]})

    return {
        "hb_human_id": human_id,
        "first_name": human.first_name,
        "middle_name": human.middle_name or "",
        "last_name": human.last_name,
        "suffix": human.suffix or "",
        "skill_value": float(human.skater_skill_value) if human.skater_skill_value is not None else None,
        "first_date": human.first_date.isoformat() if human.first_date else None,
        "last_date": human.last_date.isoformat() if human.last_date else None,
        "orgs": orgs,
        "teams": teams,
        "aliases": aliases,
    }


@identity_bp.route("/candidates", methods=["GET"])
@require_auth
def get_candidates():
    """
    GET /api/identity/candidates

    Search hockey_blast humans matching the user's name.
    Optional ?name=Pavel+Kletskov to override auto-detected name.

    Returns rich profiles: id, names, aliases, career first/last dates,
    teams with org + role + date ranges, skill value.
    """
    user = g.pred_user

    name_override = request.args.get("name", "").strip()
    parts = (name_override or user.display_name or "").split(None, 1)
    first = parts[0] if len(parts) > 0 else ""
    last = parts[1] if len(parts) > 1 else ""

    if not first and not last:
        return jsonify({"candidates": []})

    try:
        Human, HumanAlias, _, _, _, _, _ = _get_hb_models()
    except RuntimeError as exc:
        return error_response("SERVICE_UNAVAILABLE", str(exc), 503)

    hb_session = HBSession()

    try:
        # Find matching humans — search both main table and aliases
        # Main table match
        main_stmt = (
            select(Human.id)
            .where(
                Human.first_name.ilike(f"%{first}%"),
                Human.last_name.ilike(f"%{last}%"),
            )
        )
        # Alias match (catches name variations across seasons)
        alias_stmt = (
            select(HumanAlias.human_id)
            .where(
                HumanAlias.first_name.ilike(f"%{first}%"),
                HumanAlias.last_name.ilike(f"%{last}%"),
            )
        )

        main_ids = [r[0] for r in hb_session.execute(main_stmt).all()]
        alias_ids = [r[0] for r in hb_session.execute(alias_stmt).all()]
        candidate_ids = list(dict.fromkeys(main_ids + alias_ids))[:10]  # dedupe, keep order

        candidates = []
        for hid in candidate_ids:
            profile = _build_human_profile(hb_session, hid)
            if profile:
                candidates.append(profile)

        # Sort by last_date desc (most recently active first)
        candidates.sort(
            key=lambda c: c.get("last_date") or "0000-00-00",
            reverse=True,
        )

        return jsonify({"candidates": candidates})

    except Exception as exc:
        return error_response("INTERNAL_ERROR", f"Query failed: {exc}", 500)


@identity_bp.route("/confirm", methods=["POST"])
@require_auth
def confirm_identity():
    """
    POST /api/identity/confirm

    Body: { "hb_human_id": 12345 }          — claim one
       or { "hb_human_id": [123, 456] }      — claim multiple (different records = same person)
       or { "skip": true }                    — skip for now

    Each claim is appended to pred_user_hb_claims with a full profile snapshot
    (name, aliases, teams, orgs, dates) — disaster recovery: if hockey_blast is
    rebuilt from scratch and IDs change, we can re-link by name from this snapshot.

    Returns: { "linked": bool, "claims": [ {hb_human_id, is_primary, profile} ] }
    """
    from app.models.pred_user_hb_claim import PredUserHbClaim

    user = g.pred_user
    data = request.get_json(force=True, silent=True) or {}
    pred_session = PredSession()

    if data.get("skip"):
        return jsonify({"linked": False, "claims": []})

    raw = data.get("hb_human_id")
    if raw is None:
        return error_response("VALIDATION_ERROR", "Must provide 'hb_human_id' or 'skip: true'", 400)
    ids_to_claim = raw if isinstance(raw, list) else [raw]

    if not all(isinstance(i, int) and i > 0 for i in ids_to_claim):
        return error_response("VALIDATION_ERROR", "hb_human_id must be positive integer(s)", 400)

    try:
        Human, _, _, _, _, _, _ = _get_hb_models()
        hb_session = HBSession()
        for hid in ids_to_claim:
            if hb_session.get(Human, hid) is None:
                return error_response("NOT_FOUND", f"No human found with id={hid}", 404)
    except RuntimeError as exc:
        return error_response("SERVICE_UNAVAILABLE", str(exc), 503)

    # Existing claims
    existing = pred_session.execute(
        select(PredUserHbClaim).where(PredUserHbClaim.user_id == user.id)
    ).scalars().all()
    existing_ids = {c.hb_human_id for c in existing}
    has_primary = any(c.is_primary for c in existing)

    for idx, hid in enumerate(ids_to_claim):
        if hid in existing_ids:
            continue
        is_primary = not has_primary and idx == 0
        # Build and store the full profile snapshot for disaster recovery
        snapshot = _build_human_profile(hb_session, hid)
        claim = PredUserHbClaim(
            user_id=user.id,
            hb_human_id=hid,
            source="self_reported",
            is_primary=is_primary,
            profile_snapshot=snapshot,
        )
        pred_session.add(claim)
        if is_primary:
            has_primary = True
            user.hb_human_id = hid

    pred_session.commit()

    all_claims = pred_session.execute(
        select(PredUserHbClaim).where(PredUserHbClaim.user_id == user.id)
    ).scalars().all()

    return jsonify({
        "linked": True,
        "claims": [
            {
                "hb_human_id": c.hb_human_id,
                "is_primary": c.is_primary,
                "profile": c.profile_snapshot,
            }
            for c in all_claims
        ],
    })


@identity_bp.route("/my-claims", methods=["GET"])
@require_auth
def my_claims():
    """GET /api/identity/my-claims — list all identity claims for current user."""
    from app.models.pred_user_hb_claim import PredUserHbClaim

    pred_session = PredSession()
    claims = pred_session.execute(
        select(PredUserHbClaim).where(PredUserHbClaim.user_id == g.pred_user.id)
    ).scalars().all()

    return jsonify({
        "claims": [
            {
                "hb_human_id": c.hb_human_id,
                "is_primary": c.is_primary,
                "source": c.source,
                "claimed_at": c.claimed_at.isoformat() if c.claimed_at else None,
                "profile": c.profile_snapshot,
            }
            for c in claims
        ]
    })

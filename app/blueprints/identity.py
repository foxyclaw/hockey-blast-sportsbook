"""
Identity blueprint — link a PredUser to their hockey_blast human profile.

Routes:
    GET  /api/identity/candidates  — search for matching humans in hockey_blast
    POST /api/identity/confirm     — claim one or more human IDs (append-only)

Security model:
    - last_name is ALWAYS sourced from the user's Auth0 profile (pred_user.display_name)
      and cannot be overridden by the caller.  This prevents bad actors from claiming
      players they're not.
    - first_name may be supplied via ?first_name= to accommodate nicknames / data entry
      variations.  The server expands the query with known nickname synonyms so that
      "Bob" and "Robert" both return matching players.
"""

import csv
import logging
import os
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select, func, distinct, or_

from hockey_blast_common_lib.merge_humans import merge_humans

from app.auth.jwt_validator import require_auth
from app.db import HBSession, PredSession
from app.utils.response import error_response

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Nickname / synonym expansion — loaded from name_synonyms.csv
# CSV format: each row is a group of equivalent names (all interchangeable).
# e.g.  robert,bob,rob,bobby,robbie
# We build a bidirectional lookup: any name → full group.
# ---------------------------------------------------------------------------
def _load_synonyms() -> dict[str, list[str]]:
    """
    Load name synonym groups from CSV.  Each row is one equivalence group.
    A name can appear in multiple rows (e.g. 'bert' appears in 'robert' and
    'alberta' rows).  We do NOT merge rows transitively — we simply collect
    the union of all rows a name appears in, deduplicated.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "data", "name_synonyms.csv")
    # name -> set of variants seen across all rows containing that name
    synonyms: dict[str, set[str]] = {}
    try:
        with open(os.path.normpath(path), newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                group = [n.strip().lower() for n in row if n.strip()]
                if not group:
                    continue
                for name in group:
                    synonyms.setdefault(name, set()).update(group)
    except FileNotFoundError:
        pass  # graceful degradation — exact match only
    return {k: list(v) for k, v in synonyms.items()}

_SYNONYMS = _load_synonyms()


def _expand_first_name(first: str) -> list[str]:
    """Return list of name variants to search (including the original)."""
    key = first.lower()
    return _SYNONYMS.get(key, [first])

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

    # Deduplicate by team_name — keep most recent dates, OR roles across seasons
    team_map: dict[str, dict] = {}
    for r in team_rows:
        key = r.team_name
        if key not in team_map:
            team_map[key] = {
                "team_id": r.team_id,
                "team_name": r.team_name,
                "org_id": r.org_id,
                "org_name": r.org_name,
                "is_captain": r.role_type == "C",
                "first_date": r.first_date.isoformat() if r.first_date else None,
                "last_date": r.last_date.isoformat() if r.last_date else None,
            }
        else:
            # If any season was captain, mark the team as captain
            if r.role_type == "C":
                team_map[key]["is_captain"] = True
            # Keep earliest first_date, latest last_date
            if r.first_date and (not team_map[key]["first_date"] or r.first_date.isoformat() < team_map[key]["first_date"]):
                team_map[key]["first_date"] = r.first_date.isoformat()
            if r.last_date and (not team_map[key]["last_date"] or r.last_date.isoformat() > team_map[key]["last_date"]):
                team_map[key]["last_date"] = r.last_date.isoformat()

    teams = list(team_map.values())

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
    GET /api/identity/candidates[?q=<free-text>]

    Security model:
      - Both first_name and last_name are sourced exclusively from the user's
        Auth0 profile (pred_user.display_name).  The caller supplies NO params.
      - We search ALL humans whose last_name matches exactly (case-insensitive).
      - From those, we keep only records whose first_name is either:
          a) an exact match for the user's first name  → name_match = "exact"
          b) a synonym of the user's first name (via CSV) → name_match = "synonym"
        Records that don't match on first name are excluded entirely.
      - Exact matches are pre-selected by default; synonyms are selectable.

    Optional ?q= param: free-text search by first OR last name (top 10, sorted by name).
    When q is provided the standard name-security model is bypassed — results are
    returned as name_match="search" and the caller can pick any result.

    Returns:
        candidates: list of profiles, each with name_match: "exact" | "synonym" | "search"
        user_first: the first name we searched for
        user_last:  the last name we searched for (display only)
    """
    user = g.pred_user
    q = (request.args.get("q") or "").strip()

    # ── Extract first / last from Auth0 claims, falling back to display_name ─
    if user.given_name or user.family_name:
        user_first = user.given_name or ""
        user_last = user.family_name or ""
    else:
        display_parts = (user.display_name or "").rsplit(None, 1)
        user_last = display_parts[-1] if display_parts else ""
        user_first = display_parts[0] if len(display_parts) > 1 else ""

    try:
        Human, HumanAlias, _, _, _, _, _ = _get_hb_models()
    except RuntimeError as exc:
        return error_response("SERVICE_UNAVAILABLE", str(exc), 503)

    hb_session = HBSession()

    try:
        # ── Free-text search mode ────────────────────────────────────────────
        if q:
            like_q = f"%{q}%"
            from sqlalchemy import func
            main_ids = [r[0] for r in hb_session.execute(
                select(Human.id).where(
                    or_(
                        Human.first_name.ilike(like_q),
                        Human.last_name.ilike(like_q),
                        # full name match: "Dean Paganelis"
                        func.concat(Human.first_name, ' ', Human.last_name).ilike(like_q),
                        func.concat(Human.last_name, ' ', Human.first_name).ilike(like_q),
                    )
                ).order_by(Human.last_name, Human.first_name).limit(50)
            ).all()]
            alias_ids = [r[0] for r in hb_session.execute(
                select(HumanAlias.human_id).where(
                    or_(
                        HumanAlias.first_name.ilike(like_q),
                        HumanAlias.last_name.ilike(like_q),
                        func.concat(HumanAlias.first_name, ' ', HumanAlias.last_name).ilike(like_q),
                        func.concat(HumanAlias.last_name, ' ', HumanAlias.first_name).ilike(like_q),
                    )
                ).limit(50)
            ).all()]
            all_ids = list(dict.fromkeys(main_ids + alias_ids))[:50]

            candidates = []
            for hid in all_ids:
                profile = _build_human_profile(hb_session, hid)
                if not profile:
                    continue
                profile["name_match"] = "search"
                candidates.append(profile)

            # Sort by last_date desc, limit 10
            candidates.sort(key=lambda c: c.get("last_date") or "0000-00-00", reverse=True)
            candidates = candidates[:10]

            return jsonify({
                "candidates": candidates,
                "user_first": user_first,
                "user_last": user_last,
                "search_query": q,
            })

        # ── Name-security mode (default) ─────────────────────────────────────
        if not user_last:
            return jsonify({"candidates": [], "user_first": user_first, "user_last": user_last})

        # Step 1: all humans (and alias-linked humans) with matching last name
        main_ids = [r[0] for r in hb_session.execute(
            select(Human.id).where(Human.last_name.ilike(user_last))
        ).all()]
        alias_ids = [r[0] for r in hb_session.execute(
            select(HumanAlias.human_id).where(HumanAlias.last_name.ilike(user_last))
        ).all()]
        all_ids = list(dict.fromkeys(main_ids + alias_ids))

        # Step 2: build synonym set for the user's first name
        first_lower = user_first.lower()
        synonym_set = {v.lower() for v in _expand_first_name(user_first)}  # includes self

        # Step 3: filter to exact + synonym matches only; tag each
        candidates = []
        for hid in all_ids:
            profile = _build_human_profile(hb_session, hid)
            if not profile:
                continue
            rec_first = (profile.get("first_name") or "").lower()
            if rec_first == first_lower:
                profile["name_match"] = "exact"
            elif rec_first in synonym_set:
                profile["name_match"] = "synonym"
            else:
                # Also check aliases for a first-name match
                alias_firsts = {(a.get("first_name") or "").lower() for a in profile.get("aliases", [])}
                if first_lower in alias_firsts:
                    profile["name_match"] = "exact"
                elif alias_firsts & synonym_set:
                    profile["name_match"] = "synonym"
                else:
                    continue  # skip — no first-name match at all
            candidates.append(profile)

        # Sort: exact first, then synonym; within each group by last_date desc
        # Sort: exact matches first, within each group newest activity first
        exact = sorted(
            [c for c in candidates if c["name_match"] == "exact"],
            key=lambda c: c.get("last_date") or "0000-00-00", reverse=True
        )
        synonyms = sorted(
            [c for c in candidates if c["name_match"] == "synonym"],
            key=lambda c: c.get("last_date") or "0000-00-00", reverse=True
        )
        candidates = exact + synonyms

        return jsonify({
            "candidates": candidates,
            "user_first": user_first,
            "user_last": user_last,
        })

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
    # If claim came from a manual name search (not auto-matched to user's own name),
    # always require admin review regardless of conflicts
    force_pending = bool(data.get("manual_search", False))

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

    pending_review_ids = []
    for idx, hid in enumerate(ids_to_claim):
        if hid in existing_ids:
            continue
        is_primary = not has_primary and idx == 0
        # Build and store the full profile snapshot for disaster recovery
        snapshot = _build_human_profile(hb_session, hid)

        # Check if any OTHER user already has a confirmed claim for this hb_human_id
        conflicting = pred_session.execute(
            select(PredUserHbClaim).where(
                PredUserHbClaim.hb_human_id == hid,
                PredUserHbClaim.user_id != user.id,
                PredUserHbClaim.claim_status == "confirmed",
            )
        ).scalars().first()

        if conflicting or force_pending:
            claim_status = "pending_review"
            pending_review_ids.append(hid)
        else:
            claim_status = "confirmed"

        claim = PredUserHbClaim(
            user_id=user.id,
            hb_human_id=hid,
            source="manual_search" if force_pending else "self_reported",
            is_primary=is_primary and claim_status == "confirmed",
            profile_snapshot=snapshot,
            claim_status=claim_status,
        )
        pred_session.add(claim)
        if is_primary and claim_status == "confirmed":
            has_primary = True
            user.hb_human_id = hid

    pred_session.commit()

    # If all new claims were auto-confirmed (no pending_review), merge any
    # secondary human IDs into the primary one in the hockey_blast DB.
    if not pending_review_ids:
        try:
            confirmed_claims = pred_session.execute(
                select(PredUserHbClaim).where(
                    PredUserHbClaim.user_id == user.id,
                    PredUserHbClaim.claim_status == "confirmed",
                )
            ).scalars().all()

            if len(confirmed_claims) >= 2:
                primary_claim = next((c for c in confirmed_claims if c.is_primary), None)
                if primary_claim:
                    hb_merge_session = HBSession()
                    merged_secondary_claims = []
                    for secondary_claim in confirmed_claims:
                        if secondary_claim.id != primary_claim.id:
                            merge_humans(
                                hb_merge_session,
                                primary_human_id=primary_claim.hb_human_id,
                                secondary_human_id=secondary_claim.hb_human_id,
                            )
                            merged_secondary_claims.append(secondary_claim)
                    hb_merge_session.close()
                    now_utc = datetime.now(timezone.utc)
                    for sc in merged_secondary_claims:
                        sc.merged_at = now_utc
                    pred_session.commit()
        except Exception:
            _logger.exception(
                "merge_humans failed for user_id=%d after confirm_identity",
                user.id,
            )

    all_claims = pred_session.execute(
        select(PredUserHbClaim).where(PredUserHbClaim.user_id == user.id)
    ).scalars().all()

    if pending_review_ids:
        return jsonify({
            "status": "pending_review",
            "message": "This player profile is already claimed. Your claim has been submitted for admin review.",
            "linked": False,
            "pending_hb_human_ids": pending_review_ids,
            "claims": [
                {
                    "hb_human_id": c.hb_human_id,
                    "is_primary": c.is_primary,
                    "claim_status": c.claim_status,
                    "profile": c.profile_snapshot,
                }
                for c in all_claims
            ],
        }), 202

    return jsonify({
        "linked": True,
        "claims": [
            {
                "hb_human_id": c.hb_human_id,
                "is_primary": c.is_primary,
                "claim_status": c.claim_status,
                "profile": c.profile_snapshot,
            }
            for c in all_claims
        ],
    })


@identity_bp.route("/orgs", methods=["GET"])
def get_orgs():
    """GET /api/identity/orgs — list all organizations (no auth required)."""
    try:
        _, _, _, _, Organization, _, _ = _get_hb_models()
    except RuntimeError as exc:
        return error_response("SERVICE_UNAVAILABLE", str(exc), 503)

    hb_session = HBSession()
    try:
        orgs = hb_session.execute(
            select(Organization.organization_name)
            .where(Organization.id > 0)
            .order_by(Organization.organization_name)
        ).scalars().all()
        return jsonify({"orgs": list(orgs)})
    except Exception as exc:
        return error_response("INTERNAL_ERROR", str(exc), 500)


@identity_bp.route("/my-claims", methods=["GET"])
@require_auth
def my_claims():
    """GET /api/identity/my-claims — list all identity claims for current user."""
    from app.models.pred_user_hb_claim import PredUserHbClaim

    pred_session = PredSession()
    claims = pred_session.execute(
        select(PredUserHbClaim).where(
            PredUserHbClaim.user_id == g.pred_user.id,
            PredUserHbClaim.claim_status != "rejected",
        )
    ).scalars().all()

    return jsonify({
        "claims": [
            {
                "hb_human_id": c.hb_human_id,
                "is_primary": c.is_primary,
                "claim_status": c.claim_status,
                "source": c.source,
                "claimed_at": c.claimed_at.isoformat() if c.claimed_at else None,
                "profile": c.profile_snapshot,
            }
            for c in claims
        ]
    })

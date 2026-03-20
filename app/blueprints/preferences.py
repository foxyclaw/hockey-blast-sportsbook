"""
Preferences blueprint — player profile preferences.

Routes:
    GET   /api/preferences   — fetch current preferences + metadata
    PATCH /api/preferences   — upsert preferences
"""

import re

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from app.auth.jwt_validator import require_auth
from app.db import HBSession, PredSession
from app.utils.response import error_response

preferences_bp = Blueprint("preferences", __name__)


def _skill_from_value(skill_value) -> str | None:
    """Map a numeric skater skill value to a skill level label."""
    if skill_value is None:
        return None
    v = float(skill_value)
    if v <= 20:
        return "elite"
    if v <= 40:
        return "advanced"
    if v <= 60:
        return "intermediate"
    if v <= 80:
        return "recreational"
    return "beginner"


# Known state groupings for rinks in the HB database.
# Derived from city/rink knowledge since the DB has no address column populated.
_LOCATION_STATE: dict[str, str] = {
    # California — Bay Area
    "Sharks Ice At San Jose": "CA", "Sharks Ice At Oakland": "CA", "Sharks Ice At Fremont": "CA",
    "SAP Center at San Jose": "CA", "Bridgepointe Ice Arena": "CA", "Snoopy's Home Ice": "CA",
    "Livermore Ice Arena": "CA", "San Francisco Ice Arena": "CA", "Yerba Buena Ice Skating Center": "CA",
    "Skatetown Ice Arena": "CA", "Tri-Valley Ice": "CA", "Vacaville Ice Sports": "CA",
    "Redwood City Ice Lodge": "CA", "Vallco Ice Arena": "CA",
    # California — SoCal
    "Anaheim Ice": "CA", "Toyota Sports Performance Center": "CA", "Citizens Bank Arena": "CA",
    "Toyota Arena": "CA", "The Rinks - Lake Forest": "CA", "Aliso Viejo Ice Palace": "CA",
    "Yorba Linda Ice": "CA", "Ontario Center Ice": "CA", "Ontario Ice Skating Center": "CA",
    "Artesia Ice Rink": "CA", "Paramount Iceland": "CA", "Lakewood Ice": "CA",
    "Poway Ice": "CA", "Carlsbad Ice Center": "CA", "San Diego Ice Arena": "CA",
    "Kroc Center Ice Arena": "CA", "Escondido Ice Plex": "CA",
    "University of California San Diego Ice Arena": "CA", "Westminster Ice Palace": "CA",
    "Pasadena Ice Skating Center": "CA", "Pickwick Ice": "CA",
    "Ice Station Valencia": "CA", "Iceoplex Simi Valley": "CA",
    "Oak Park Ice Arena": "CA", "Bakersfield Ice Sports Center": "CA",
    "Palm Desert Ice Castle": "CA", "Riverside Ice": "CA",
    "Mechanics Bank Arena": "CA", "Selland Arena": "CA",
    "America First Field at Heart of Hacienda Heights": "CA",
    "Highland Ice Arena": "CA",
    # California — NorCal other
    "South Lake Tahoe Ice Arena": "CA", "Mammoth Ice Rink": "CA",
    "Ice in Paradise": "CA", "Bay Harbor Ice Rink": "CA",
    # Nevada
    "Las Vegas Ice Center": "NV", "City National Arena": "NV", "Reno Ice": "NV",
    "Tahoe Blue Center": "NV",
    # Oregon
    "Winterhawks Skating Center": "OR",
    # Washington
    "Tacoma Twin Rinks": "WA", "Kent Highland Ice Arena": "WA",
    "Kent Valley Ice Centre": "WA", "Sprinker Recreation Center": "WA",
    "Bremerton Ice Center": "WA", "Olympic View Arena": "WA",
    "Snoqualmie Ice Arena": "WA", "Inline Hockey Club of Kirkland": "WA",
    "accesso ShoWare Center": "WA",
    # Other / unknown
    "Sherwood Ice Arena": "OR",
}

_STATE_NAMES = {
    "CA": "California", "NV": "Nevada", "OR": "Oregon", "WA": "Washington",
    "Other": "Other",
}


def _get_locations():
    """Return list of canonical locations grouped by state from HB DB."""
    try:
        from hockey_blast_common_lib.models import Location
        from sqlalchemy import distinct
    except ImportError:
        return []

    hb_session = HBSession()
    try:
        subq = select(distinct(Location.master_location_id)).where(
            Location.master_location_id.isnot(None)
        ).scalar_subquery()

        rows = hb_session.execute(
            select(Location.id, Location.location_name)
            .where(Location.id.in_(subq))
            .where(Location.location_name.isnot(None))
            .order_by(Location.location_name)
        ).all()

        # Deduplicate by name, skip junk entries
        skip_names = {"NHL", "Outside Area"}
        seen: dict[str, int] = {}
        for r in rows:
            if r.location_name not in seen and r.location_name not in skip_names:
                seen[r.location_name] = r.id

        # Group by state
        groups: dict[str, list] = {}
        for name, lid in seen.items():
            state = _LOCATION_STATE.get(name, "Other")
            state_label = _STATE_NAMES.get(state, state)
            if state_label not in groups:
                groups[state_label] = []
            groups[state_label].append({"id": lid, "name": name})

        # Return as sorted list of {state, locations[]}
        return [
            {"state": state, "locations": locs}
            for state, locs in sorted(groups.items())
        ]
    except Exception:
        return []


def _get_locations_for_human(hb_human_id: int) -> list[int]:
    """Return list of master location IDs where a human has played."""
    try:
        from hockey_blast_common_lib.models import GameRoster, Game, Location
    except ImportError:
        return []

    hb_session = HBSession()
    try:
        # Get all game_ids the human played in
        rows = hb_session.execute(
            select(Game.location_id)
            .join(GameRoster, GameRoster.game_id == Game.id)
            .where(GameRoster.human_id == hb_human_id)
            .where(Game.location_id.isnot(None))
        ).all()

        raw_location_ids = {r.location_id for r in rows}
        if not raw_location_ids:
            return []

        # Resolve to master locations
        loc_rows = hb_session.execute(
            select(Location.id, Location.master_location_id)
            .where(Location.id.in_(raw_location_ids))
        ).all()

        master_ids: set[int] = set()
        for loc in loc_rows:
            if loc.master_location_id is not None:
                master_ids.add(loc.master_location_id)
            else:
                master_ids.add(loc.id)  # it IS the master

        return list(master_ids)
    except Exception:
        return []
    finally:
        hb_session.close()


def _get_captain_candidates(user):
    """
    Build captain candidates list from all of the user's HB claim snapshots.
    Returns list of {team_id, team_name, org_name, already_claimed}.
    """
    from app.models.pred_user_hb_claim import PredUserHbClaim
    from app.models.pred_user_captain_claim import PredUserCaptainClaim

    pred_session = PredSession()

    # Only use confirmed claims — pending/rejected claims don't grant captain rights
    claims = pred_session.execute(
        select(PredUserHbClaim).where(
            PredUserHbClaim.user_id == user.id,
            PredUserHbClaim.claim_status == "confirmed",
        )
    ).scalars().all()

    # Existing captain claim team IDs
    existing_captain_ids = {
        r.team_id
        for r in pred_session.execute(
            select(PredUserCaptainClaim).where(
                PredUserCaptainClaim.user_id == user.id,
                PredUserCaptainClaim.is_active == True,  # noqa: E712
            )
        ).scalars().all()
    }

    # Gather captain teams from snapshots — deduplicate by team_id
    seen_team_ids: set[int] = set()
    candidates = []
    for claim in claims:
        snapshot = claim.profile_snapshot or {}
        for team in snapshot.get("teams", []):
            if not team.get("is_captain"):
                continue
            team_id = team.get("team_id")
            if team_id is None or team_id in seen_team_ids:
                continue
            seen_team_ids.add(team_id)
            candidates.append(
                {
                    "team_id": team_id,
                    "team_name": team.get("team_name", ""),
                    "org_name": team.get("org_name"),
                    "already_claimed": team_id in existing_captain_ids,
                }
            )

    return candidates


def _team_lookup_from_snapshot(user, team_id: int) -> dict:
    """Find team_name / org_name for a given team_id from the user's claim snapshots."""
    from app.models.pred_user_hb_claim import PredUserHbClaim

    pred_session = PredSession()
    claims = pred_session.execute(
        select(PredUserHbClaim).where(PredUserHbClaim.user_id == user.id)
    ).scalars().all()

    for claim in claims:
        snapshot = claim.profile_snapshot or {}
        for team in snapshot.get("teams", []):
            if team.get("team_id") == team_id:
                return {
                    "team_name": team.get("team_name", f"Team {team_id}"),
                    "org_name": team.get("org_name"),
                }
    return {"team_name": f"Team {team_id}", "org_name": None}


# ── GET /api/preferences ───────────────────────────────────────────────────────

@preferences_bp.route("", methods=["GET"])
@require_auth
def get_preferences():
    """Return current user preferences with metadata for the form."""
    from app.models.pred_user_preferences import PredUserPreferences
    from app.models.pred_user_captain_claim import PredUserCaptainClaim
    from app.models.pred_user_hb_claim import PredUserHbClaim

    user = g.pred_user
    pred_session = PredSession()

    # Fetch or build default prefs dict
    prefs_obj = pred_session.execute(
        select(PredUserPreferences).where(PredUserPreferences.user_id == user.id)
    ).scalar_one_or_none()

    if prefs_obj:
        prefs = prefs_obj.to_dict()
    else:
        prefs = {
            "skill_level": None,
            "is_free_agent": False,
            "wants_to_sub": False,
            "notify_email": True,
            "notify_phone": None,
            "interested_location_ids": [],
            "skill_level_comment": None,
        }

    # Suggested skill level from primary claim's profile_snapshot
    suggested_skill_level = None
    primary_claim = pred_session.execute(
        select(PredUserHbClaim).where(
            PredUserHbClaim.user_id == user.id,
            PredUserHbClaim.is_primary == True,  # noqa: E712
        )
    ).scalar_one_or_none()
    if primary_claim and primary_claim.profile_snapshot:
        skill_val = primary_claim.profile_snapshot.get("skill_value")
        suggested_skill_level = _skill_from_value(skill_val)

    # Auto-pre-select locations if the user has no saved preferences and has claims
    if not prefs["interested_location_ids"]:
        all_claims = pred_session.execute(
            select(PredUserHbClaim).where(PredUserHbClaim.user_id == user.id)
        ).scalars().all()
        auto_location_ids: set[int] = set()
        for claim in all_claims:
            ids = _get_locations_for_human(claim.hb_human_id)
            auto_location_ids.update(ids)
        if auto_location_ids:
            prefs["interested_location_ids"] = list(auto_location_ids)

    # Captain candidates
    captain_candidates = _get_captain_candidates(user)

    # Active captain claims
    active_captain_claims = pred_session.execute(
        select(PredUserCaptainClaim).where(
            PredUserCaptainClaim.user_id == user.id,
            PredUserCaptainClaim.is_active == True,  # noqa: E712
        )
    ).scalars().all()

    # Locations
    locations = _get_locations()

    return jsonify(
        {
            "preferences": prefs,
            "suggested_skill_level": suggested_skill_level,
            "captain_candidates": captain_candidates,
            "active_captain_claims": [c.to_dict() for c in active_captain_claims],
            "locations": locations,
        }
    )


# ── PATCH /api/preferences ─────────────────────────────────────────────────────

@preferences_bp.route("", methods=["PATCH"])
@require_auth
def update_preferences():
    """Upsert user preferences."""
    from app.models.pred_user_preferences import PredUserPreferences
    from app.models.pred_user_captain_claim import PredUserCaptainClaim

    user = g.pred_user
    data = request.get_json(force=True, silent=True) or {}
    pred_session = PredSession()

    # ── Validate phone ─────────────────────────────────────────────────────────
    raw_phone = data.get("notify_phone") or ""
    notify_phone = None
    if raw_phone:
        digits = re.sub(r"\D", "", raw_phone)
        if not (10 <= len(digits) <= 15):
            return error_response(
                "VALIDATION_ERROR",
                "Phone number must be 10-15 digits",
                400,
            )
        notify_phone = digits

    # ── Upsert PredUserPreferences ─────────────────────────────────────────────
    prefs_obj = pred_session.execute(
        select(PredUserPreferences).where(PredUserPreferences.user_id == user.id)
    ).scalar_one_or_none()

    if prefs_obj is None:
        prefs_obj = PredUserPreferences(user_id=user.id)
        pred_session.add(prefs_obj)

    if "skill_level" in data:
        prefs_obj.skill_level = data["skill_level"] or None
    if "is_free_agent" in data:
        prefs_obj.is_free_agent = bool(data["is_free_agent"])
    if "wants_to_sub" in data:
        prefs_obj.wants_to_sub = bool(data["wants_to_sub"])
    if "notify_email" in data:
        prefs_obj.notify_email = bool(data["notify_email"])
    prefs_obj.notify_phone = notify_phone if raw_phone else prefs_obj.notify_phone
    if "notify_phone" in data and not raw_phone:
        prefs_obj.notify_phone = None
    if "interested_location_ids" in data:
        prefs_obj.interested_location_ids = data["interested_location_ids"] or []
    if "skill_level_comment" in data:
        raw_comment = (data["skill_level_comment"] or "").strip()
        if len(raw_comment) > 500:
            return error_response(
                "VALIDATION_ERROR",
                "Skill level comment must be 500 characters or fewer",
                400,
            )
        prefs_obj.skill_level_comment = raw_comment or None

    # ── Handle captain claims ──────────────────────────────────────────────────
    if "captain_team_ids" in data:
        requested_ids: list[int] = [int(t) for t in (data["captain_team_ids"] or [])]

        existing_claims = {
            c.team_id: c
            for c in pred_session.execute(
                select(PredUserCaptainClaim).where(
                    PredUserCaptainClaim.user_id == user.id
                )
            ).scalars().all()
        }

        # Upsert requested
        for team_id in requested_ids:
            if team_id in existing_claims:
                existing_claims[team_id].is_active = True
            else:
                info = _team_lookup_from_snapshot(user, team_id)
                claim = PredUserCaptainClaim(
                    user_id=user.id,
                    team_id=team_id,
                    team_name=info["team_name"],
                    org_name=info["org_name"],
                    is_active=True,
                )
                pred_session.add(claim)

        # Deactivate claims not in requested list
        for team_id, claim_obj in existing_claims.items():
            if team_id not in requested_ids:
                claim_obj.is_active = False

    # ── Mark preferences completed ─────────────────────────────────────────────
    from app.models.pred_user import PredUser
    db_user = pred_session.get(PredUser, user.id)
    if db_user:
        db_user.preferences_completed = True

    pred_session.commit()

    return jsonify(
        {
            "preferences": prefs_obj.to_dict(),
            "preferences_completed": user.preferences_completed,
        }
    )

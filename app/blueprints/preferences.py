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


# State + city for each rink
_LOCATION_META: dict[str, tuple[str, str]] = {
    # (state, city)
    # Bay Area
    "Sharks Ice At San Jose":           ("CA", "San Jose"),
    "SAP Center at San Jose":           ("CA", "San Jose"),
    "Bridgepointe Ice Arena":           ("CA", "San Jose"),
    "Sharks Ice At Fremont":            ("CA", "Fremont"),
    "Sharks Ice At Oakland":            ("CA", "Oakland"),
    "San Francisco Ice Arena":          ("CA", "San Francisco"),
    "Yerba Buena Ice Skating Center":   ("CA", "San Francisco"),
    "Redwood City Ice Lodge":           ("CA", "Redwood City"),
    "Skatetown Ice Arena":              ("CA", "Roseville"),
    "Snoopy's Home Ice":                ("CA", "Santa Rosa"),
    "Livermore Ice Arena":              ("CA", "Livermore"),
    "Tri-Valley Ice":                   ("CA", "Dublin"),
    "Vacaville Ice Sports":             ("CA", "Vacaville"),
    "Vallco Ice Arena":                 ("CA", "Cupertino"),
    "Bay Harbor Ice Rink":              ("CA", "San Mateo"),
    # NorCal other
    "Ice in Paradise":                  ("CA", "Grass Valley"),
    "South Lake Tahoe Ice Arena":       ("CA", "South Lake Tahoe"),
    "Mammoth Ice Rink":                 ("CA", "Mammoth Lakes"),
    # SoCal — LA / OC
    "Anaheim Ice":                      ("CA", "Anaheim"),
    "Toyota Sports Performance Center": ("CA", "El Segundo"),
    "Citizens Bank Arena":              ("CA", "Ontario"),
    "Toyota Arena":                     ("CA", "Ontario"),
    "Ontario Center Ice":               ("CA", "Ontario"),
    "Ontario Ice Skating Center":       ("CA", "Ontario"),
    "The Rinks - Lake Forest":          ("CA", "Lake Forest"),
    "Aliso Viejo Ice Palace":           ("CA", "Aliso Viejo"),
    "Yorba Linda Ice":                  ("CA", "Yorba Linda"),
    "Artesia Ice Rink":                 ("CA", "Artesia"),
    "Paramount Iceland":                ("CA", "Paramount"),
    "Lakewood Ice":                     ("CA", "Lakewood"),
    "Pasadena Ice Skating Center":      ("CA", "Pasadena"),
    "Pickwick Ice":                     ("CA", "Burbank"),
    "Ice Station Valencia":             ("CA", "Valencia"),
    "Iceoplex Simi Valley":             ("CA", "Simi Valley"),
    "Oak Park Ice Arena":               ("CA", "Oak Park"),
    "Highland Ice Arena":               ("CA", "Highland"),
    "America First Field at Heart of Hacienda Heights": ("CA", "Hacienda Heights"),
    # SoCal — San Diego
    "Poway Ice":                        ("CA", "Poway"),
    "Carlsbad Ice Center":              ("CA", "Carlsbad"),
    "San Diego Ice Arena":              ("CA", "San Diego"),
    "Kroc Center Ice Arena":            ("CA", "San Diego"),
    "Escondido Ice Plex":               ("CA", "Escondido"),
    "University of California San Diego Ice Arena": ("CA", "San Diego"),
    "Westminster Ice Palace":           ("CA", "Westminster"),
    # SoCal — Inland / Central Valley
    "Bakersfield Ice Sports Center":    ("CA", "Bakersfield"),
    "Mechanics Bank Arena":             ("CA", "Bakersfield"),
    "Selland Arena":                    ("CA", "Fresno"),
    "Palm Desert Ice Castle":           ("CA", "Palm Desert"),
    "Riverside Ice":                    ("CA", "Riverside"),
    # Nevada
    "Las Vegas Ice Center":             ("NV", "Las Vegas"),
    "City National Arena":              ("NV", "Las Vegas"),
    "Reno Ice":                         ("NV", "Reno"),
    "Tahoe Blue Center":                ("NV", "Stateline"),
    # Oregon
    "Winterhawks Skating Center":       ("OR", "Portland"),
    "Sherwood Ice Arena":               ("OR", "Sherwood"),
    # Washington
    "Tacoma Twin Rinks":                ("WA", "Tacoma"),
    "Sprinker Recreation Center":       ("WA", "Tacoma"),
    "Kent Highland Ice Arena":          ("WA", "Kent"),
    "Kent Valley Ice Centre":           ("WA", "Kent"),
    "accesso ShoWare Center":           ("WA", "Kent"),
    "Bremerton Ice Center":             ("WA", "Bremerton"),
    "Olympic View Arena":               ("WA", "Bremerton"),
    "Snoqualmie Ice Arena":             ("WA", "Snoqualmie"),
    "Inline Hockey Club of Kirkland":   ("WA", "Kirkland"),
}

_STATE_NAMES = {
    "CA": "California", "NV": "Nevada", "OR": "Oregon", "WA": "Washington",
    "Other": "Other",
}

# Backwards compat
_LOCATION_STATE: dict[str, str] = {k: v[0] for k, v in _LOCATION_META.items()}


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

        # Group by state → city
        # structure: { state_label: { city: [ {id, name} ] } }
        groups: dict[str, dict[str, list]] = {}
        for name, lid in seen.items():
            state_code, city = _LOCATION_META.get(name, ("Other", "Other"))
            state_label = _STATE_NAMES.get(state_code, state_code)
            if state_label not in groups:
                groups[state_label] = {}
            if city not in groups[state_label]:
                groups[state_label][city] = []
            groups[state_label][city].append({"id": lid, "name": name})

        # Return as sorted list of {state, cities: [{city, locations[]}]}
        return [
            {
                "state": state,
                "cities": [
                    {"city": city, "locations": sorted(locs, key=lambda x: x["name"])}
                    for city, locs in sorted(cities.items())
                ]
            }
            for state, cities in sorted(groups.items())
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

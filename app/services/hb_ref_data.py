"""
Batched + cached loaders for hockey_blast reference rows.

Each function takes a collection of ids for a whole page of games/picks and
resolves them with at most one ``WHERE id IN (...)`` query per table (fewer with
warm cache), returning a dict keyed by id.  Ids that do not exist map to ``None``.

The caches hold plain Python data (never ORM instances) so entries are safe to
reuse across requests and sessions.  Loaders raise on DB errors — callers decide
whether to swallow (the old per-id helpers in the blueprints did).
"""

from collections.abc import Iterable

from sqlalchemy import select

from app.services.ref_cache import TTLCache, load_cached

team_cache = TTLCache()
division_cache = TTLCache()
level_cache = TTLCache()
org_cache = TTLCache()
skill_cache = TTLCache()  # team_id -> avg skill (float) or None


def clear_all_caches() -> None:
    for cache in (team_cache, division_cache, level_cache, org_cache, skill_cache):
        cache.clear()


def get_team_names(team_ids: Iterable[int | None], hb_session) -> dict[int, str | None]:
    """{team_id: name} — one query for all uncached ids."""

    def _load(ids: list) -> dict:
        from hockey_blast_common_lib.models import Team

        rows = hb_session.execute(select(Team.id, Team.name).where(Team.id.in_(ids))).all()
        return {row.id: row.name for row in rows}

    return load_cached(team_cache, team_ids, _load)


def get_orgs(org_ids: Iterable[int | None], hb_session) -> dict[int, dict | None]:
    """{org_id: {"id", "name"}} in the shape /api/games returns."""

    def _load(ids: list) -> dict:
        from hockey_blast_common_lib.models import Organization

        rows = hb_session.execute(
            select(Organization.id, Organization.organization_name).where(Organization.id.in_(ids))
        ).all()
        return {row.id: row.organization_name for row in rows}

    names = load_cached(org_cache, org_ids, _load)
    return {
        org_id: ({"id": org_id, "name": name} if name is not None else None)
        for org_id, name in names.items()
    }


def get_levels(level_ids: Iterable[int | None], hb_session) -> dict[int, dict | None]:
    """{level_id: {"short_name", "level_name"}}."""

    def _load(ids: list) -> dict:
        from hockey_blast_common_lib.models import Level

        rows = hb_session.execute(
            select(Level.id, Level.short_name, Level.level_name).where(Level.id.in_(ids))
        ).all()
        return {
            row.id: {"short_name": row.short_name, "level_name": row.level_name} for row in rows
        }

    return load_cached(level_cache, level_ids, _load)


def get_divisions(division_ids: Iterable[int | None], hb_session) -> dict[int, dict | None]:
    """
    {division_id: {"id", "name", "short_name"}} in the shape /api/games returns.

    Mirrors the old per-id ``_get_division``: name is ``Division.level``; short_name
    prefers ``Level.short_name`` then ``Level.level_name`` then ``Division.level``.
    Two queries at most (divisions, then their levels), regardless of page size.
    """

    def _load(ids: list) -> dict:
        from hockey_blast_common_lib.models import Division

        rows = hb_session.execute(
            select(Division.id, Division.level, Division.level_id).where(Division.id.in_(ids))
        ).all()
        return {row.id: {"level": row.level, "level_id": row.level_id} for row in rows}

    divisions = load_cached(division_cache, division_ids, _load)
    level_ids = [d["level_id"] for d in divisions.values() if d and d["level_id"]]
    levels = get_levels(level_ids, hb_session) if level_ids else {}

    out: dict[int, dict | None] = {}
    for div_id, div in divisions.items():
        if div is None:
            out[div_id] = None
            continue
        short_name = None
        lvl = levels.get(div["level_id"]) if div["level_id"] else None
        if lvl:
            short_name = lvl["short_name"] or lvl["level_name"]
        out[div_id] = {
            "id": div_id,
            "name": div["level"],  # full name e.g. "Adult Division 4B"
            "short_name": short_name or div["level"],  # e.g. "4B"
        }
    return out


def get_team_avg_skills_cached(
    team_ids: Iterable[int | None], hb_session
) -> dict[int, float | None]:
    """
    {team_id: avg skater skill or None} — the heaviest lookup on the games page,
    so it sits behind the same TTL cache.  Misses are resolved by ONE windowed
    query (skill_snapshot.get_team_avg_skills); teams with no data cache as None.
    """
    from app.services.skill_snapshot import get_team_avg_skills

    return load_cached(skill_cache, team_ids, lambda ids: get_team_avg_skills(ids, hb_session))

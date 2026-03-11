"""
Skill snapshot — captures team average skill at pick submission time.

Skill data comes from hockey_blast_common_lib's OrgStatsSkater table.
skill_value: 0 = elite, 100 = worst.

We snapshot at pick time because skill values change throughout the season.
Point-in-time fairness: the upset bonus is based on who was the underdog
when you made your pick, not who ended up winning the season.
"""

from sqlalchemy import func, select

from app.db import HBSession


def get_team_avg_skill(team_id: int, org_id: int) -> float | None:
    """
    Return the average skater_skill_value for a team's rostered skaters
    using the pre-aggregated org_stats_skater table.

    Returns None if:
      - No stats found (new team, no history)
      - hockey_blast_common_lib not installed (returns None gracefully)
    """
    try:
        from hockey_blast_common_lib.models import OrgStatsSkater
    except ImportError:
        return None

    session = HBSession()
    stmt = select(func.avg(OrgStatsSkater.skater_skill_value)).where(
        OrgStatsSkater.team_id == team_id,
        OrgStatsSkater.org_id == org_id,
    )
    result = session.execute(stmt).scalar_one_or_none()
    return float(result) if result is not None else None


def get_game_skill_snapshot(game_id: int) -> dict:
    """
    Fetch skill averages for both teams in a game.

    Returns a dict with:
        home_team_avg_skill:   float | None
        away_team_avg_skill:   float | None
        picked_team_avg_skill: None (caller fills this in)
        opponent_avg_skill:    None (caller fills this in)
        skill_differential:    None (caller fills this in)
        is_upset_pick:         False (caller fills this in)

    Caller is responsible for computing the pick-specific fields.
    """
    try:
        from hockey_blast_common_lib.models import Game
    except ImportError:
        return _empty_snapshot()

    session = HBSession()
    stmt = select(Game).where(Game.id == game_id)
    game = session.execute(stmt).scalar_one_or_none()

    if game is None:
        return _empty_snapshot()

    # We need the org_id to look up stats.
    # Games belong to a season which belongs to an org — try game.org_id or game.season.org_id
    org_id = getattr(game, "org_id", None)
    if org_id is None:
        # Try to get it via season relationship
        season = getattr(game, "season", None)
        if season:
            org_id = getattr(season, "org_id", None)

    if org_id is None:
        return _empty_snapshot()

    home_skill = get_team_avg_skill(game.home_team_id, org_id)
    away_skill = get_team_avg_skill(game.away_team_id, org_id)

    return {
        "home_team_avg_skill": home_skill,
        "away_team_avg_skill": away_skill,
        "picked_team_avg_skill": None,   # filled by pick_service
        "opponent_avg_skill": None,       # filled by pick_service
        "skill_differential": None,       # filled by pick_service
        "is_upset_pick": False,           # filled by pick_service
    }


def compute_pick_skill_fields(
    picked_team_id: int,
    home_team_id: int,
    away_team_id: int,
    home_skill: float | None,
    away_skill: float | None,
) -> dict:
    """
    Given the picked team and both teams' skill values, compute:
        picked_team_avg_skill
        opponent_avg_skill
        skill_differential  (picked - opponent; positive = upset pick)
        is_upset_pick
    """
    if picked_team_id == home_team_id:
        picked_skill = home_skill
        opp_skill = away_skill
    elif picked_team_id == away_team_id:
        picked_skill = away_skill
        opp_skill = home_skill
    else:
        # Shouldn't happen — validation in pick_service catches this
        return {
            "picked_team_avg_skill": None,
            "opponent_avg_skill": None,
            "skill_differential": None,
            "is_upset_pick": False,
        }

    if picked_skill is not None and opp_skill is not None:
        diff = picked_skill - opp_skill
        is_upset = diff > 0  # Higher skill value = worse team = upset if they win
    else:
        diff = None
        is_upset = False

    return {
        "picked_team_avg_skill": picked_skill,
        "opponent_avg_skill": opp_skill,
        "skill_differential": diff,
        "is_upset_pick": is_upset,
    }


def _empty_snapshot() -> dict:
    return {
        "home_team_avg_skill": None,
        "away_team_avg_skill": None,
        "picked_team_avg_skill": None,
        "opponent_avg_skill": None,
        "skill_differential": None,
        "is_upset_pick": False,
    }

"""
Skill snapshot — captures team average skill at pick submission time.

Skill data: Human.skater_skill_value (0 = elite, 100 = worst) aggregated
via GameRoster to find recent skaters for a team.

We snapshot at pick time because skill values change throughout the season.
"""

from sqlalchemy import func, select

from app.db import HBSession


def get_team_avg_skill(team_id: int, org_id: int | None = None) -> float | None:
    """
    Return the average skater_skill_value for a team's skaters via GameRoster.
    Looks at up to the last 200 roster entries to keep it fast.

    Returns None if no data found or lib not installed.
    """
    try:
        from hockey_blast_common_lib.models import GameRoster, Human
    except ImportError:
        return None

    session = HBSession()

    # Get recent skaters for this team (role='skater')
    recent_stmt = (
        select(GameRoster.human_id)
        .where(GameRoster.team_id == team_id, GameRoster.role != "G")
        .order_by(GameRoster.id.desc())
        .limit(200)
        .subquery()
    )

    skill_stmt = select(func.avg(Human.skater_skill_value)).where(
        Human.id.in_(select(recent_stmt.c.human_id)),
        Human.skater_skill_value.isnot(None),
    )
    result = session.execute(skill_stmt).scalar_one_or_none()
    return float(result) if result is not None else None


def get_game_skill_snapshot(game_id: int) -> dict:
    """
    Fetch skill averages for both teams in a game.
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

    org_id = getattr(game, "org_id", None)
    home_skill = get_team_avg_skill(game.home_team_id, org_id)
    visitor_skill = get_team_avg_skill(game.visitor_team_id, org_id)

    return {
        "home_team_avg_skill": home_skill,
        "away_team_avg_skill": visitor_skill,
        "picked_team_avg_skill": None,
        "opponent_avg_skill": None,
        "skill_differential": None,
        "is_upset_pick": False,
    }


def compute_pick_skill_fields(
    picked_team_id: int,
    home_team_id: int,
    visitor_team_id: int,
    home_skill: float | None,
    visitor_skill: float | None,
) -> dict:
    """
    Compute picked/opponent skill fields given both team IDs and skills.
    """
    if picked_team_id == home_team_id:
        picked_skill = home_skill
        opp_skill = visitor_skill
    elif picked_team_id == visitor_team_id:
        picked_skill = visitor_skill
        opp_skill = home_skill
    else:
        return {
            "picked_team_avg_skill": None,
            "opponent_avg_skill": None,
            "skill_differential": None,
            "is_upset_pick": False,
        }

    if picked_skill is not None and opp_skill is not None:
        diff = picked_skill - opp_skill
        is_upset = diff > 0  # Higher value = worse team = upset pick
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

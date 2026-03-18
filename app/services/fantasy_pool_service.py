"""
fantasy_pool_service — builds the eligible player pool for a fantasy league.

Uses HBSession (read-only) to query level stats for skaters and goalies from
the most recent season for the given level.
"""

from sqlalchemy import select, func

from app.db import HBSession


def get_player_pool(level_id: int) -> dict:
    """
    Returns the eligible player pool for a fantasy league at the given HB level.

    Returns:
        {
            "skaters": [{ hb_human_id, first_name, last_name, games_played,
                          goals, assists, points, penalties, ppg, is_goalie }, ...],
            "goalies": [{ ... is_goalie: True }, ...],
            "roster_skaters": int,
            "max_managers": int,
        }
    """
    from hockey_blast_common_lib.stats_models import LevelStatsSkater, LevelStatsGoalie
    from hockey_blast_common_lib.models import Human

    hb = HBSession()

    # ── Skaters ──────────────────────────────────────────────────────────────
    skater_stmt = (
        select(
            LevelStatsSkater.human_id,
            Human.first_name,
            Human.last_name,
            LevelStatsSkater.games_played,
            LevelStatsSkater.goals,
            LevelStatsSkater.assists,
            LevelStatsSkater.penalties,
        )
        .join(Human, Human.id == LevelStatsSkater.human_id)
        .where(
            LevelStatsSkater.level_id == level_id,
            LevelStatsSkater.games_played >= 3,
        )
        .order_by(LevelStatsSkater.games_played.desc())
    )

    skater_rows = hb.execute(skater_stmt).all()
    skaters = []
    for row in skater_rows:
        gp = row.games_played or 1
        pts = (row.goals or 0) + (row.assists or 0)
        ppg = round(pts / gp, 3)
        skaters.append({
            "hb_human_id": row.human_id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "games_played": row.games_played,
            "goals": row.goals or 0,
            "assists": row.assists or 0,
            "points": pts,
            "penalties": row.penalties or 0,
            "ppg": ppg,
            "is_goalie": False,
        })

    # ── Goalies ───────────────────────────────────────────────────────────────
    goalie_stmt = (
        select(
            LevelStatsGoalie.human_id,
            Human.first_name,
            Human.last_name,
            LevelStatsGoalie.games_played,
        )
        .join(Human, Human.id == LevelStatsGoalie.human_id)
        .where(
            LevelStatsGoalie.level_id == level_id,
            LevelStatsGoalie.games_played >= 2,
        )
        .order_by(LevelStatsGoalie.games_played.desc())
    )

    goalie_rows = hb.execute(goalie_stmt).all()
    goalies = []
    for row in goalie_rows:
        gp = row.games_played or 1
        goalies.append({
            "hb_human_id": row.human_id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "games_played": row.games_played,
            "goals": 0,
            "assists": 0,
            "points": 0,
            "penalties": 0,
            "ppg": 0.0,
            "is_goalie": True,
        })

    # ── Roster sizing formula ─────────────────────────────────────────────────
    pool_size = len(skaters)
    usable = int(pool_size * 0.7)
    roster_skaters = 5  # minimum
    for r in range(10, 4, -1):
        if usable // r >= 4:
            roster_skaters = r
            break

    max_managers = min(12, usable // roster_skaters) if roster_skaters > 0 else 4
    max_managers = max(4, max_managers)

    return {
        "skaters": skaters,
        "goalies": goalies,
        "roster_skaters": roster_skaters,
        "max_managers": max_managers,
    }

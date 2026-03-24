"""
fantasy_pool_service — builds the eligible player pool for a fantasy league.

Uses HBSession (read-only) to query division-level stats for skaters and goalies
from the most recent season for the given level/org. Fantasy points are computed
from stats.
"""

from sqlalchemy import select, func

from app.db import HBSession


def get_player_pool(level_id: int, org_id: int = 1, league_id: int = None, season_id: int = None) -> dict:
    """
    Returns the eligible player pool for a fantasy league at the given HB level.

    Fantasy scoring:
      Skaters: fantasy_points = (goals * 3) + (assists * 2) + (games_played * 1) - (penalties * 0.5)
               fantasy_ppg    = fantasy_points / games_played
      Goalies:  fantasy_points = (wins * 5) + (shutouts * 3) + (games_played * 1)

    Returns:
        {
            "skaters": [...sorted by fantasy_ppg DESC...],
            "goalies": [...sorted by fantasy_points DESC...],
            "roster_skaters": int,
            "max_managers": int,
        }
    """
    from hockey_blast_common_lib.stats_models import DivisionStatsSkater, DivisionStatsGoalie
    from hockey_blast_common_lib.models import Human, Division, Season
    from hockey_blast_common_lib.utils import get_non_human_ids

    hb = HBSession()

    # Exclude fake/placeholder players
    non_human_ids = get_non_human_ids(hb)

    # Find the most recent season_id for this level, org, and optionally league
    from hockey_blast_common_lib.models import Season as HBSeason
    season_filter = [
        Division.level_id == level_id,
        Division.org_id == org_id,
    ]
    if league_id is not None:
        season_filter.append(
            Division.season_id.in_(
                select(HBSeason.id).where(
                    HBSeason.league_id == league_id,
                    HBSeason.org_id == org_id,
                )
            )
        )

    if season_id is not None:
        # Admin-pinned season — use it directly
        div_ids_stmt = select(Division.id).where(
            Division.level_id == level_id,
            Division.season_id == season_id,
        )
    else:
        season_subq = (
            select(func.max(Division.season_id))
            .where(*season_filter)
            .scalar_subquery()
        )
        div_ids_stmt = select(Division.id).where(
            Division.level_id == level_id,
            Division.org_id == org_id,
            Division.season_id == season_subq,
        )

    # ── Skaters ──────────────────────────────────────────────────────────────
    skater_stmt = (
        select(
            DivisionStatsSkater.human_id,
            Human.first_name,
            Human.last_name,
            func.sum(DivisionStatsSkater.games_played).label("games_played"),
            func.sum(DivisionStatsSkater.goals).label("goals"),
            func.sum(DivisionStatsSkater.assists).label("assists"),
            func.sum(DivisionStatsSkater.points).label("points"),
            func.sum(DivisionStatsSkater.penalties).label("penalties"),
        )
        .join(Human, Human.id == DivisionStatsSkater.human_id)
        .where(DivisionStatsSkater.division_id.in_(div_ids_stmt))
        .where(DivisionStatsSkater.human_id.not_in(non_human_ids) if non_human_ids else True)
        .group_by(DivisionStatsSkater.human_id, Human.first_name, Human.last_name)
        .having(func.sum(DivisionStatsSkater.games_played) >= 1)
    )

    skater_rows = hb.execute(skater_stmt).all()
    skaters = []
    for row in skater_rows:
        gp = row.games_played or 1
        goals = row.goals or 0
        assists = row.assists or 0
        penalties = row.penalties or 0
        pts = goals + assists
        fantasy_points = (goals * 3) + (assists * 2) + (gp * 1) - (penalties * 0.5)
        fantasy_ppg = round(fantasy_points / gp, 3) if gp > 0 else 0.0
        skaters.append({
            "hb_human_id": row.human_id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "games_played": row.games_played,
            "goals": goals,
            "assists": assists,
            "points": pts,
            "penalties": penalties,
            "fantasy_points": round(fantasy_points, 2),
            "fantasy_ppg": fantasy_ppg,
            "is_goalie": False,
        })

    # Sort by total fantasy points descending (FP); FPPG is available as secondary column
    skaters.sort(key=lambda p: p["fantasy_points"], reverse=True)

    # ── Goalies ───────────────────────────────────────────────────────────────
    goalie_stmt = (
        select(
            DivisionStatsGoalie.human_id,
            Human.first_name,
            Human.last_name,
            func.sum(DivisionStatsGoalie.games_played).label("games_played"),
            func.sum(DivisionStatsGoalie.goals_allowed).label("goals_allowed"),
            func.sum(DivisionStatsGoalie.shots_faced).label("shots_faced"),
            func.avg(DivisionStatsGoalie.goals_allowed_per_game).label("goals_against_avg"),
            func.avg(DivisionStatsGoalie.save_percentage).label("save_percentage"),
        )
        .join(Human, Human.id == DivisionStatsGoalie.human_id)
        .where(DivisionStatsGoalie.division_id.in_(div_ids_stmt))
        .where(DivisionStatsGoalie.human_id.not_in(non_human_ids) if non_human_ids else True)
        .group_by(DivisionStatsGoalie.human_id, Human.first_name, Human.last_name)
        .having(func.sum(DivisionStatsGoalie.games_played) >= 1)
    )

    goalie_rows = hb.execute(goalie_stmt).all()
    goalies = []
    for row in goalie_rows:
        gp = row.games_played or 1
        # DivisionStatsGoalie has no wins/shutouts columns, derive what we can
        # Use games_played as base; fantasy_points = gp * 1 + (save_pct bonus)
        # Since no wins/shutouts: fantasy_points = games_played * 1
        # (saves-based proxy: save_pct * 3 bonus per game if > 0.9)
        save_pct = float(row.save_percentage or 0)
        gaa = float(row.goals_against_avg or 0)
        fantasy_points = float(gp) * 1.0 + (save_pct * 5.0 * gp)
        goalies.append({
            "hb_human_id": row.human_id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "games_played": row.games_played,
            "goals_allowed": int(row.goals_allowed or 0),
            "shots_faced": int(row.shots_faced or 0),
            "goals_against_avg": round(gaa, 3),
            "save_percentage": round(save_pct, 3),
            "fantasy_points": round(fantasy_points, 2),
            "fantasy_ppg": round(fantasy_points / gp, 3) if gp > 0 else 0.0,
            "is_goalie": True,
            # Keep compatibility fields
            "goals": 0,
            "assists": 0,
            "points": 0,
            "penalties": 0,
        })

    # Sort by fantasy_points descending
    goalies.sort(key=lambda p: p["fantasy_points"], reverse=True)

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

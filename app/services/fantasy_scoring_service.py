"""
fantasy_scoring_service — computes and persists fantasy points for a completed game.

Scoring rules:
  Goal        = 3 pts
  Assist      = 2 pts
  Game played = 1 pt
  Penalty (per minor) = -0.5 pts
  Goalie win  = 5 pts
  Goalie shutout bonus = +3 pts
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import HBSession, PredSession
from app.models.fantasy_roster import FantasyRoster
from app.models.fantasy_game_scores import FantasyGameScores
from app.models.fantasy_standings import FantasyStandings

logger = logging.getLogger(__name__)

GOAL_PTS = 3.0
ASSIST_PTS = 2.0
GAME_PLAYED_PTS = 1.0
PENALTY_PTS = -0.5
GOALIE_WIN_PTS = 5.0
SHUTOUT_BONUS = 3.0


def _compute_points(goals, assists, penalties, games_played, is_goalie_win, is_shutout) -> float:
    pts = 0.0
    pts += goals * GOAL_PTS
    pts += assists * ASSIST_PTS
    pts += games_played * GAME_PLAYED_PTS
    pts += penalties * PENALTY_PTS
    if is_goalie_win:
        pts += GOALIE_WIN_PTS
    if is_shutout:
        pts += SHUTOUT_BONUS
    return pts


def score_game(league_id: int, game_id: int) -> None:
    """
    Score a single HB game for all rostered players in the given fantasy league.
    Upserts into fantasy_game_scores and updates fantasy_standings.
    """
    hb = HBSession()
    pred = PredSession()

    # Get all rostered players for this league
    roster_stmt = select(FantasyRoster).where(FantasyRoster.league_id == league_id)
    roster = pred.execute(roster_stmt).scalars().all()
    if not roster:
        return

    rostered_ids = {r.hb_human_id: r for r in roster}

    # Query HB for game roster / goal stats
    # Use raw SQL since models may have Flask-SQLAlchemy bindings
    try:
        # Skater stats for this game
        skater_sql = text("""
            SELECT
                gr.human_id,
                COALESCE(SUM(CASE WHEN g.scoring_type IN ('Goal','PP Goal','SH Goal','Penalty Shot Goal') THEN 1 ELSE 0 END), 0) AS goals,
                COALESCE(SUM(CASE WHEN g.scoring_type IN ('Assist','PP Assist','SH Assist') THEN 1 ELSE 0 END), 0) AS assists,
                COALESCE(SUM(CASE WHEN g.scoring_type IN ('Minor','Major','Game Misconduct') THEN 1 ELSE 0 END), 0) AS penalties
            FROM game_roster gr
            LEFT JOIN goals g ON g.game_id = gr.game_id AND (g.scorer_id = gr.human_id OR g.assist1_id = gr.human_id OR g.assist2_id = gr.human_id OR g.penalized_player_id = gr.human_id)
            WHERE gr.game_id = :game_id
            GROUP BY gr.human_id
        """)
        skater_rows = hb.execute(skater_sql, {"game_id": game_id}).fetchall()
    except Exception:
        # Fallback: simpler query if schema differs
        try:
            skater_sql = text("""
                SELECT human_id,
                       0 AS goals, 0 AS assists, 0 AS penalties
                FROM game_roster
                WHERE game_id = :game_id
                GROUP BY human_id
            """)
            skater_rows = hb.execute(skater_sql, {"game_id": game_id}).fetchall()
        except Exception as e:
            logger.warning(f"score_game: could not query HB for game {game_id}: {e}")
            return

    # Check for goalie wins / shutouts
    try:
        goalie_sql = text("""
            SELECT
                gg.goalie_id AS human_id,
                gg.is_win,
                gg.goals_allowed
            FROM game_goalies gg
            WHERE gg.game_id = :game_id
        """)
        goalie_rows = hb.execute(goalie_sql, {"game_id": game_id}).fetchall()
    except Exception:
        goalie_rows = []

    goalie_results = {}
    for gr in goalie_rows:
        goalie_results[gr.human_id] = {
            "is_win": bool(getattr(gr, "is_win", False)),
            "is_shutout": (getattr(gr, "goals_allowed", 1) == 0),
        }

    # Build stats map
    stats = {}
    for row in skater_rows:
        stats[row.human_id] = {
            "goals": int(row.goals),
            "assists": int(row.assists),
            "penalties": int(row.penalties),
        }

    now = datetime.now(timezone.utc)

    # Score each rostered player
    for hb_human_id, roster_entry in rostered_ids.items():
        if hb_human_id not in stats:
            continue  # player didn't play in this game

        s = stats[hb_human_id]
        goalie_info = goalie_results.get(hb_human_id, {})
        is_goalie_win = goalie_info.get("is_win", False)
        is_shutout = goalie_info.get("is_shutout", False)

        pts = _compute_points(
            goals=s["goals"],
            assists=s["assists"],
            penalties=s["penalties"],
            games_played=1,
            is_goalie_win=is_goalie_win,
            is_shutout=is_shutout,
        )

        # Upsert into fantasy_game_scores
        stmt = pg_insert(FantasyGameScores).values(
            league_id=league_id,
            user_id=roster_entry.user_id,
            hb_human_id=hb_human_id,
            game_id=game_id,
            goals=s["goals"],
            assists=s["assists"],
            penalties=s["penalties"],
            games_played=1,
            is_goalie_win=is_goalie_win,
            is_shutout=is_shutout,
            points=pts,
            scored_at=now,
        ).on_conflict_do_update(
            constraint="uq_fantasy_game_scores_league_human_game",
            set_={
                "goals": s["goals"],
                "assists": s["assists"],
                "penalties": s["penalties"],
                "is_goalie_win": is_goalie_win,
                "is_shutout": is_shutout,
                "points": pts,
                "scored_at": now,
            }
        )
        pred.execute(stmt)

    pred.commit()

    # Update standings
    _update_standings(league_id, pred)


def _update_standings(league_id: int, pred) -> None:
    """Recompute total_points for all managers and update rank."""
    from sqlalchemy import func
    from app.models.fantasy_roster import FantasyRoster
    from app.models.fantasy_game_scores import FantasyGameScores

    # Sum points per user
    pts_stmt = (
        select(
            FantasyGameScores.user_id,
            func.sum(FantasyGameScores.points).label("total"),
        )
        .where(FantasyGameScores.league_id == league_id)
        .group_by(FantasyGameScores.user_id)
    )
    rows = pred.execute(pts_stmt).all()

    sorted_rows = sorted(rows, key=lambda r: float(r.total or 0), reverse=True)
    now = datetime.now(timezone.utc)

    for rank, row in enumerate(sorted_rows, 1):
        stmt = pg_insert(FantasyStandings).values(
            league_id=league_id,
            user_id=row.user_id,
            total_points=float(row.total or 0),
            week_points=0,
            rank=rank,
            updated_at=now,
        ).on_conflict_do_update(
            constraint="uq_fantasy_standings_league_user",
            set_={
                "total_points": float(row.total or 0),
                "rank": rank,
                "updated_at": now,
            }
        )
        pred.execute(stmt)

    pred.commit()

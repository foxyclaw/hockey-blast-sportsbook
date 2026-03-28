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
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import HBSession, PredSession
from app.models.fantasy_roster import FantasyRoster
from app.models.fantasy_game_scores import FantasyGameScores
from app.models.fantasy_standings import FantasyStandings

logger = logging.getLogger(__name__)

GOAL_PTS = 3.0
# Ref scoring
REF_GAME_PTS = 1.0
REF_PENALTY_PTS = 1.5
REF_GM_PTS = 8.0
ASSIST_PTS = 2.0
GAME_PLAYED_PTS = 1.0
PENALTY_PTS = -0.5
GOALIE_WIN_PTS = 5.0
SHUTOUT_BONUS = 3.0


def _compute_points(goals, assists, penalties, games_played, is_goalie_win, is_shutout,
                    ref_games=0, ref_penalties=0, ref_gm=0) -> float:
    pts = 0.0
    pts += goals * GOAL_PTS
    pts += assists * ASSIST_PTS
    pts += games_played * GAME_PLAYED_PTS
    pts += penalties * PENALTY_PTS
    if is_goalie_win:
        pts += GOALIE_WIN_PTS
    if is_shutout:
        pts += SHUTOUT_BONUS
    # Ref scoring
    pts += ref_games * REF_GAME_PTS
    pts += ref_penalties * REF_PENALTY_PTS
    pts += ref_gm * REF_GM_PTS
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

    # ── Get all players who appeared in this game (game_rosters) ─────────────
    try:
        participants = {
            r.human_id
            for r in hb.execute(
                text("SELECT human_id FROM game_rosters WHERE game_id = :gid"),
                {"gid": game_id},
            ).fetchall()
        }
    except Exception as e:
        logger.warning("score_game: could not query game_rosters for game %d: %s", game_id, e)
        try:
            hb.rollback()
        except Exception:
            pass
        try:
            hb.rollback()
        except Exception:
            pass
        return

    # ── Goals: goal_scorer_id, assist_1_id, assist_2_id ──────────────────────
    goals_by_player: dict[int, int] = {}
    assists_by_player: dict[int, int] = {}
    try:
        goal_rows = hb.execute(
            text("SELECT goal_scorer_id, assist_1_id, assist_2_id "
                 "FROM goals WHERE game_id = :gid"),
            {"gid": game_id},
        ).fetchall()
        for g in goal_rows:
            if g.goal_scorer_id:
                goals_by_player[g.goal_scorer_id] = goals_by_player.get(g.goal_scorer_id, 0) + 1
            if g.assist_1_id:
                assists_by_player[g.assist_1_id] = assists_by_player.get(g.assist_1_id, 0) + 1
            if g.assist_2_id:
                assists_by_player[g.assist_2_id] = assists_by_player.get(g.assist_2_id, 0) + 1
    except Exception as e:
        logger.warning("score_game: could not query goals for game %d: %s", game_id, e)
        try:
            hb.rollback()
        except Exception:
            pass

    # ── Penalties: penalized_player_id ───────────────────────────────────────
    penalties_by_player: dict[int, int] = {}
    try:
        pen_rows = hb.execute(
            text("SELECT penalized_player_id FROM penalties WHERE game_id = :gid"),
            {"gid": game_id},
        ).fetchall()
        for p in pen_rows:
            if p.penalized_player_id:
                penalties_by_player[p.penalized_player_id] = (
                    penalties_by_player.get(p.penalized_player_id, 0) + 1
                )
    except Exception as e:
        logger.warning("score_game: could not query penalties for game %d: %s", game_id, e)
        try:
            hb.rollback()
        except Exception:
            pass

    # ── Goalie win/shutout from games table ───────────────────────────────────
    goalie_results: dict[int, dict] = {}
    try:
        game_row = hb.execute(
            text("SELECT home_goalie_id, visitor_goalie_id, "
                 "home_final_score, visitor_final_score FROM games WHERE id = :gid"),
            {"gid": game_id},
        ).fetchone()
        if game_row and game_row.home_final_score is not None and game_row.visitor_final_score is not None:
            h = game_row.home_final_score
            v = game_row.visitor_final_score
            if game_row.home_goalie_id:
                goalie_results[game_row.home_goalie_id] = {
                    "is_win":     h > v,
                    "is_shutout": v == 0,
                }
            if game_row.visitor_goalie_id:
                goalie_results[game_row.visitor_goalie_id] = {
                    "is_win":     v > h,
                    "is_shutout": h == 0,
                }
    except Exception as e:
        logger.warning("score_game: could not query goalie data for game %d: %s", game_id, e)
        try:
            hb.rollback()
        except Exception:
            pass

    # ── Referee stats for this game ──────────────────────────────────────────
    ref_stats: dict[int, dict] = {}
    try:
        ref_rows = hb.execute(
            text("SELECT human_id FROM ref_divisions WHERE game_id = :gid"),
            {"gid": game_id},
        ).fetchall()
        for r in ref_rows:
            if r.human_id not in ref_stats:
                ref_stats[r.human_id] = {"games": 1, "penalties": 0, "gm": 0}
        # Count penalties called by each ref in this game
        ref_pen_rows = hb.execute(
            text("""SELECT referee_id,
                    COUNT(*) AS cnt,
                    SUM(CASE WHEN LOWER(penalty_type) LIKE '%game misconduct%' THEN 1 ELSE 0 END) AS gm_cnt
                    FROM penalties WHERE game_id = :gid AND referee_id IS NOT NULL
                    GROUP BY referee_id"""),
            {"gid": game_id},
        ).fetchall()
        for r in ref_pen_rows:
            if r.referee_id in ref_stats:
                ref_stats[r.referee_id]["penalties"] = int(r.cnt or 0)
                ref_stats[r.referee_id]["gm"] = int(r.gm_cnt or 0)
    except Exception as e:
        logger.debug("score_game: ref stats unavailable for game %d: %s", game_id, e)
        try:
            hb.rollback()
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    scored = 0

    # ── Score each rostered player who was in this game ───────────────────────
    for hb_human_id, roster_entry in rostered_ids.items():
        # Refs score from ref_stats, not game_rosters
        if roster_entry.is_ref:
            if hb_human_id not in ref_stats:
                continue
            rs = ref_stats[hb_human_id]
            pts = _compute_points(
                goals=0, assists=0, penalties=0, games_played=0,
                is_goalie_win=False, is_shutout=False,
                ref_games=rs["games"], ref_penalties=rs["penalties"], ref_gm=rs["gm"],
            )
            stmt = pg_insert(FantasyGameScores).values(
                league_id=league_id,
                user_id=roster_entry.user_id,
                hb_human_id=hb_human_id,
                game_id=game_id,
                goals=0, assists=0, penalties=0, games_played=0,
                is_goalie_win=False, is_shutout=False,
                ref_games=rs["games"], ref_penalties=rs["penalties"], ref_gm=rs["gm"],
                points=pts, scored_at=now,
            ).on_conflict_do_update(
                constraint="uq_fantasy_game_scores_league_human_game",
                set_={"ref_games": rs["games"], "ref_penalties": rs["penalties"],
                      "ref_gm": rs["gm"], "points": pts, "scored_at": now}
            )
            pred.execute(stmt)
            scored += 1
            continue

        if hb_human_id not in participants:
            continue  # player didn't appear in this game

        goals     = goals_by_player.get(hb_human_id, 0)
        assists   = assists_by_player.get(hb_human_id, 0)
        penalties = penalties_by_player.get(hb_human_id, 0)
        goalie_info  = goalie_results.get(hb_human_id, {})
        is_goalie_win = goalie_info.get("is_win", False)
        is_shutout    = goalie_info.get("is_shutout", False)

        pts = _compute_points(
            goals=goals,
            assists=assists,
            penalties=penalties,
            games_played=1,
            is_goalie_win=is_goalie_win,
            is_shutout=is_shutout,
        )

        stmt = pg_insert(FantasyGameScores).values(
            league_id=league_id,
            user_id=roster_entry.user_id,
            hb_human_id=hb_human_id,
            game_id=game_id,
            goals=goals,
            assists=assists,
            penalties=penalties,
            games_played=1,
            is_goalie_win=is_goalie_win,
            is_shutout=is_shutout,
            points=pts,
            scored_at=now,
        ).on_conflict_do_update(
            constraint="uq_fantasy_game_scores_league_human_game",
            set_={
                "goals":         goals,
                "assists":       assists,
                "penalties":     penalties,
                "is_goalie_win": is_goalie_win,
                "is_shutout":    is_shutout,
                "points":        pts,
                "scored_at":     now,
            }
        )
        pred.execute(stmt)
        scored += 1

    pred.commit()
    logger.info("score_game: league=%d game=%d scored=%d players", league_id, game_id, scored)

    # ── Update standings ──────────────────────────────────────────────────────
    _update_standings(league_id, pred)


def resolve_and_cache_division(league_id: int) -> int | None:
    """
    Look up division_id for a league from HB (level_id + hb_season_id),
    cache it on the league row, and return it. Returns None if not found.
    """
    pred = PredSession()
    hb = HBSession()
    from app.models.fantasy_league import FantasyLeague
    league = pred.get(FantasyLeague, league_id)
    if not league or not league.hb_season_id:
        return None
    rows = hb.execute(
        text("SELECT id FROM divisions WHERE level_id = :lvl AND season_id = :sid AND org_id = :org LIMIT 1"),
        {"lvl": league.level_id, "sid": league.hb_season_id, "org": league.org_id},
    ).fetchall()
    if not rows:
        return None
    div_id = rows[0].id
    if league.hb_division_id != div_id:
        league.hb_division_id = div_id
        pred.commit()
    return div_id


def score_active_leagues() -> dict:
    """
    Find all active fantasy leagues, discover completed-but-unscored games,
    and score them. Called by the background scheduler.

    Returns summary: {"leagues": int, "games": int, "errors": int}
    """
    pred = PredSession()
    summary = {"leagues": 0, "games": 0, "errors": 0}

    try:
        from app.models.fantasy_league import FantasyLeague
        leagues = pred.execute(
            select(FantasyLeague).where(FantasyLeague.status == "active")
        ).scalars().all()
    except Exception as e:
        logger.exception("[fantasy] Could not load active leagues: %s", e)
        return summary

    for league in leagues:
        summary["leagues"] += 1
        hb = HBSession()  # Fresh session per league to avoid transaction cascade failures
        try:
            # Use cached division_id when available for fast lookup
            if league.hb_division_id:
                div_ids_sql = str(league.hb_division_id)
            else:
                div_rows = hb.execute(
                    text("SELECT id FROM divisions WHERE level_id = :lvl AND season_id = :sid AND org_id = :org"),
                    {"lvl": league.level_id, "sid": league.hb_season_id, "org": league.org_id},
                ).fetchall()
                if not div_rows:
                    continue
                div_ids_sql = ",".join(str(r.id) for r in div_rows)
                # Cache it for next time
                try:
                    pred.execute(
                        text("UPDATE fantasy_leagues SET hb_division_id=:did WHERE id=:lid"),
                        {"did": div_rows[0].id, "lid": league.id}
                    )
                    pred.commit()
                except Exception:
                    pred.rollback()
            final_games = hb.execute(
                text(
                    f"SELECT id FROM games WHERE division_id IN ({div_ids_sql}) "
                    "AND status IN ('Final','Final.','Final/OT','Final/OT2','Final/SO','Final(SO)')"
                )
            ).fetchall()

            if not final_games:
                continue

            already_scored = {
                r.game_id
                for r in pred.execute(
                    text("SELECT DISTINCT game_id FROM fantasy_game_scores WHERE league_id = :lid"),
                    {"lid": league.id},
                ).fetchall()
            }

            for game_row in final_games:
                if game_row.id in already_scored:
                    continue
                try:
                    score_game(league.id, game_row.id)
                    summary["games"] += 1
                except Exception as ge:
                    logger.warning("[fantasy] score_game(%d, %d) failed: %s", league.id, game_row.id, ge)
                    summary["errors"] += 1

        except Exception as le:
            logger.exception("[fantasy] Error processing league %d: %s", league.id, le)
            summary["errors"] += 1
            try:
                hb.rollback()
            except Exception:
                pass

    return summary


def _update_standings(league_id: int, pred) -> None:
    """Recompute total_points and week_points for all managers and update rank."""
    from sqlalchemy import func

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Total points
    pts_stmt = (
        select(
            FantasyGameScores.user_id,
            func.sum(FantasyGameScores.points).label("total"),
        )
        .where(FantasyGameScores.league_id == league_id)
        .group_by(FantasyGameScores.user_id)
    )
    total_rows = pred.execute(pts_stmt).all()
    total_map = {r.user_id: float(r.total or 0) for r in total_rows}

    # Week points — join to HB games table to get actual game date
    # Falls back to scored_at if game date not available
    try:
        from app.db import HBSession
        from sqlalchemy import text as sa_text
        hb = HBSession()
        # Get game_ids for this league scored in last 7 days (by scored_at as proxy)
        # Then cross-check actual game.date from HB
        game_ids_stmt = (
            select(FantasyGameScores.game_id)
            .where(FantasyGameScores.league_id == league_id)
            .distinct()
        )
        all_game_ids = [r.game_id for r in pred.execute(game_ids_stmt).all()]
        if all_game_ids:
            ids_sql = ",".join(str(g) for g in all_game_ids)
            recent_games = hb.execute(sa_text(
                f"SELECT id FROM games WHERE id IN ({ids_sql}) AND date >= :cutoff"
            ), {"cutoff": week_ago.date()}).fetchall()
            recent_game_ids = {r.id for r in recent_games}
        else:
            recent_game_ids = set()

        week_stmt = (
            select(
                FantasyGameScores.user_id,
                func.sum(FantasyGameScores.points).label("week_total"),
            )
            .where(
                FantasyGameScores.league_id == league_id,
                FantasyGameScores.game_id.in_(recent_game_ids) if recent_game_ids else False,
            )
            .group_by(FantasyGameScores.user_id)
        )
        week_rows = pred.execute(week_stmt).all()
        week_map = {r.user_id: float(r.week_total or 0) for r in week_rows}
    except Exception as e:
        logger.warning("week_points calculation failed, falling back to 0: %s", e)
        week_map = {}
        try:
            hb.rollback()
        except Exception:
            pass

    sorted_users = sorted(total_map.keys(), key=lambda uid: total_map[uid], reverse=True)

    for rank, user_id in enumerate(sorted_users, 1):
        stmt = pg_insert(FantasyStandings).values(
            league_id=league_id,
            user_id=user_id,
            total_points=total_map[user_id],
            week_points=week_map.get(user_id, 0.0),
            rank=rank,
            updated_at=now,
        ).on_conflict_do_update(
            constraint="uq_fantasy_standings_league_user",
            set_={
                "total_points": total_map[user_id],
                "week_points":  week_map.get(user_id, 0.0),
                "rank":         rank,
                "updated_at":   now,
            }
        )
        pred.execute(stmt)

    pred.commit()

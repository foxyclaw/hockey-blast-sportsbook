"""
fantasy_scoring_service — computes and persists fantasy points for a completed game.

Scoring rules:
  Goal        = 3 pts
  Assist      = 2 pts
  Game played = 1 pt (skaters) / 3 pts (goalies)
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
REF_GAME_PTS = 4.0
REF_PENALTY_PTS = 2.0
REF_GM_PTS = 8.0
ASSIST_PTS = 2.0
GAME_PLAYED_PTS = 1.0
GOALIE_GAME_PLAYED_PTS = 3.0
PENALTY_PTS = -0.5
GOALIE_WIN_PTS = 5.0
SHUTOUT_BONUS = 3.0


def _compute_points(goals, assists, penalties, games_played, is_goalie_win, is_shutout,
                    ref_games=0, ref_penalties=0, ref_gm=0, is_goalie=False) -> float:
    pts = 0.0
    pts += goals * GOAL_PTS
    pts += assists * ASSIST_PTS
    per_game_pts = GOALIE_GAME_PLAYED_PTS if is_goalie else GAME_PLAYED_PTS
    pts += games_played * per_game_pts
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
    # Refs are recorded on games.referee_1_id / referee_2_id. (The old code queried
    # ref_divisions.game_id and penalties.referee_id — neither column exists — so
    # ref scoring silently produced nothing.) There is no per-ref penalty/GM
    # attribution available, so refs score on games officiated only.
    ref_stats: dict[int, dict] = {}
    try:
        game_ref_row = hb.execute(
            text("SELECT referee_1_id, referee_2_id FROM games WHERE id = :gid"),
            {"gid": game_id},
        ).fetchone()
        if game_ref_row:
            for rid in (game_ref_row.referee_1_id, game_ref_row.referee_2_id):
                if rid:
                    ref_stats[rid] = {"games": 1, "penalties": 0, "gm": 0}
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
                points=pts, scored_at=now, is_provisional=False,
            ).on_conflict_do_update(
                constraint="uq_fantasy_game_scores_league_human_game",
                set_={"ref_games": rs["games"], "ref_penalties": rs["penalties"],
                      "ref_gm": rs["gm"], "points": pts, "scored_at": now,
                      "is_provisional": False}
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
            is_goalie=roster_entry.is_goalie,
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
            is_provisional=False,
        ).on_conflict_do_update(
            constraint="uq_fantasy_game_scores_league_human_game",
            set_={
                "goals":          goals,
                "assists":        assists,
                "penalties":      penalties,
                "is_goalie_win":  is_goalie_win,
                "is_shutout":     is_shutout,
                "points":         pts,
                "scored_at":      now,
                "is_provisional": False,
            }
        )
        pred.execute(stmt)
        scored += 1

    pred.commit()
    logger.info("score_game: league=%d game=%d scored=%d players", league_id, game_id, scored)

    # ── Update standings ──────────────────────────────────────────────────────
    _update_standings(league_id, pred)


def score_live_game(league_id: int, game_id: int) -> None:
    """
    Provisionally score an in-progress (OPEN) HB game for all rostered players.
    Skips goalie win/shutout (not yet decided). Marks rows is_provisional=True.
    Upserts into fantasy_game_scores and updates fantasy_standings.
    """
    hb = HBSession()
    pred = PredSession()

    roster_stmt = select(FantasyRoster).where(FantasyRoster.league_id == league_id)
    roster = pred.execute(roster_stmt).scalars().all()
    if not roster:
        return

    rostered_ids = {r.hb_human_id: r for r in roster}

    try:
        participants = {
            r.human_id
            for r in hb.execute(
                text("SELECT human_id FROM game_rosters WHERE game_id = :gid"),
                {"gid": game_id},
            ).fetchall()
        }
    except Exception as e:
        logger.warning("score_live_game: could not query game_rosters for game %d: %s", game_id, e)
        try:
            hb.rollback()
        except Exception:
            pass
        return

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
        logger.warning("score_live_game: could not query goals for game %d: %s", game_id, e)
        try:
            hb.rollback()
        except Exception:
            pass

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
        logger.warning("score_live_game: could not query penalties for game %d: %s", game_id, e)
        try:
            hb.rollback()
        except Exception:
            pass

    # Ref stats — refs are on games.referee_1_id / referee_2_id (see score_game).
    # Games officiated only; no per-ref penalty/GM data source.
    ref_stats: dict[int, dict] = {}
    try:
        game_ref_row = hb.execute(
            text("SELECT referee_1_id, referee_2_id FROM games WHERE id = :gid"),
            {"gid": game_id},
        ).fetchone()
        if game_ref_row:
            for rid in (game_ref_row.referee_1_id, game_ref_row.referee_2_id):
                if rid:
                    ref_stats[rid] = {"games": 1, "penalties": 0, "gm": 0}
    except Exception as e:
        logger.debug("score_live_game: ref stats unavailable for game %d: %s", game_id, e)
        try:
            hb.rollback()
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    scored = 0

    for hb_human_id, roster_entry in rostered_ids.items():
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
                points=pts, scored_at=now, is_provisional=True,
            ).on_conflict_do_update(
                constraint="uq_fantasy_game_scores_league_human_game",
                set_={"ref_games": rs["games"], "ref_penalties": rs["penalties"],
                      "ref_gm": rs["gm"], "points": pts, "scored_at": now,
                      "is_provisional": True}
            )
            pred.execute(stmt)
            scored += 1
            continue

        if hb_human_id not in participants:
            continue

        goals     = goals_by_player.get(hb_human_id, 0)
        assists   = assists_by_player.get(hb_human_id, 0)
        penalties = penalties_by_player.get(hb_human_id, 0)

        # Goalie win/shutout NOT available in-progress — skip
        pts = _compute_points(
            goals=goals,
            assists=assists,
            penalties=penalties,
            games_played=1,
            is_goalie_win=False,
            is_shutout=False,
            is_goalie=roster_entry.is_goalie,
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
            is_goalie_win=False,
            is_shutout=False,
            points=pts,
            scored_at=now,
            is_provisional=True,
        ).on_conflict_do_update(
            constraint="uq_fantasy_game_scores_league_human_game",
            set_={
                "goals":          goals,
                "assists":        assists,
                "penalties":      penalties,
                "is_goalie_win":  False,
                "is_shutout":     False,
                "points":         pts,
                "scored_at":      now,
                "is_provisional": True,
            }
        )
        pred.execute(stmt)
        scored += 1

    pred.commit()
    logger.debug("score_live_game: league=%d game=%d scored=%d players (provisional)",
                 league_id, game_id, scored)

    _update_standings(league_id, pred)


def score_live_games() -> dict:
    """
    Find OPEN games in active leagues' divisions and score them provisionally.
    Re-scores previously-provisional games (so live points stay current),
    but skips games already finalized (is_provisional=False rows exist).
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
        logger.exception("[fantasy-live] Could not load active leagues: %s", e)
        return summary

    for league in leagues:
        summary["leagues"] += 1
        hb = HBSession()
        try:
            if league.hb_division_id:
                div_ids_sql = str(league.hb_division_id)
            else:
                continue  # need cached division for fast lookup; final scorer fills this in

            date_filter = ""
            date_params = {}
            if league.season_starts_at:
                date_filter = " AND date >= :season_start"
                date_params = {"season_start": league.season_starts_at.date()}

            open_games = hb.execute(
                text(
                    f"SELECT id FROM games WHERE division_id IN ({div_ids_sql}) "
                    f"AND status_id = 9{date_filter}"  # 9=OPEN (canonical status_id)
                ),
                date_params or None,
            ).fetchall()

            if not open_games:
                continue

            already_finalized = {
                r.game_id
                for r in pred.execute(
                    text("SELECT DISTINCT game_id FROM fantasy_game_scores "
                         "WHERE league_id = :lid AND is_provisional = FALSE"),
                    {"lid": league.id},
                ).fetchall()
            }

            for game_row in open_games:
                if game_row.id in already_finalized:
                    continue
                try:
                    score_live_game(league.id, game_row.id)
                    summary["games"] += 1
                except Exception as ge:
                    logger.warning("[fantasy-live] score_live_game(%d, %d) failed: %s",
                                   league.id, game_row.id, ge)
                    summary["errors"] += 1

        except Exception as le:
            logger.exception("[fantasy-live] Error processing league %d: %s", league.id, le)
            summary["errors"] += 1
            try:
                hb.rollback()
            except Exception:
                pass

    return summary


def auto_assign_seasons() -> dict:
    """
    For every active league where hb_season_id IS NULL and season_starts_at <= now,
    look for a HB season newer than draft_season_id for the same level/org/hb_league_id.
    If found, assign it and trigger resolve_and_cache_division.
    If not found, skip silently (will retry next run).
    Returns {"checked": int, "assigned": int, "errors": int}
    """
    from datetime import datetime, timezone as _tz
    from sqlalchemy import select, func
    from app.db import PredSession, HBSession
    from app.models.fantasy_league import FantasyLeague

    summary = {"checked": 0, "assigned": 0, "errors": 0}
    now = datetime.now(_tz.utc)

    pred = PredSession()
    try:
        leagues = pred.execute(
            select(FantasyLeague).where(
                FantasyLeague.status == "active",
                FantasyLeague.hb_season_id.is_(None),
                FantasyLeague.season_starts_at <= now,
            )
        ).scalars().all()
    except Exception as e:
        logger.exception("[auto-season] Could not load leagues: %s", e)
        return summary

    for league in leagues:
        summary["checked"] += 1
        try:
            hb = HBSession()
            # Find newest season for this level/org that is NEWER than the draft season
            # If draft_season_id is None, we just want any season (fallback)
            query_params = {"lvl": league.level_id, "org": league.org_id}
            if league.hb_league_id:
                query_params["hb_league_id"] = league.hb_league_id
                extra_filter = "AND s.league_id = :hb_league_id"
            else:
                extra_filter = ""

            if league.draft_season_id:
                query_params["draft_sid"] = league.draft_season_id
                draft_filter = "AND d.season_id > :draft_sid"
            else:
                draft_filter = ""

            row = hb.execute(
                text(
                    f"SELECT MAX(d.season_id) as new_sid FROM divisions d "
                    f"JOIN seasons s ON s.id = d.season_id "
                    f"WHERE d.level_id = :lvl AND d.org_id = :org "
                    f"{extra_filter} {draft_filter}"
                ),
                query_params,
            ).fetchone()

            new_season_id = row.new_sid if row else None
            if not new_season_id:
                continue  # No new season yet — retry next run

            league.hb_season_id = new_season_id
            league.hb_division_id = None  # Will be resolved below
            pred.commit()
            resolve_and_cache_division(league.id)
            summary["assigned"] += 1
            logger.info(
                "[auto-season] League %d assigned new season_id=%d (was draft_season_id=%s)",
                league.id, new_season_id, league.draft_season_id,
            )
        except Exception as e:
            summary["errors"] += 1
            logger.exception("[auto-season] Error processing league %d: %s", league.id, e)

    return summary


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
            date_filter = ""
            date_params = {}
            if league.season_starts_at:
                date_filter = " AND date >= :season_start"
                date_params = {"season_start": league.season_starts_at.date()}

            final_games = hb.execute(
                text(
                    f"SELECT id FROM games WHERE division_id IN ({div_ids_sql}) "
                    # status_id 3=FINAL, 4=FINAL_OT, 5=FINAL_SO. The legacy string
                    # filter used mixed-case 'Final'... which no longer matches the
                    # canonical uppercase status values, so finalization never ran.
                    f"AND status_id IN (3, 4, 5){date_filter}"
                ),
                date_params or None,
            ).fetchall()

            if not final_games:
                continue

            # Only treat games as already-scored when their rows are non-provisional.
            # Provisional rows from live scoring should be re-scored to finalize them.
            already_scored = {
                r.game_id
                for r in pred.execute(
                    text("SELECT DISTINCT game_id FROM fantasy_game_scores "
                         "WHERE league_id = :lid AND is_provisional = FALSE"),
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


def compute_in_window_fp(league_id: int, hb_human_ids: list[int]) -> dict[int, dict]:
    """
    Compute each player's fantasy points using the SAME per-game scoring formula
    and the SAME game window that standings use — i.e. FINAL games in the league's
    tracked division on/after season_starts_at. Returns
    {hb_human_id: {"skater": fp, "goalie": fp, "ref": fp}}.

    This is what should be shown next to players during a trade: the number equals
    what the player would actually contribute to standings, NOT the whole-season
    division-stat aggregate from the draft pool (which ignores season_starts_at and
    uses a different goalie formula).
    """
    result: dict[int, dict] = {h: {"skater": 0.0, "goalie": 0.0, "ref": 0.0} for h in hb_human_ids}
    if not hb_human_ids:
        return result

    from app.models.fantasy_league import FantasyLeague
    pred = PredSession()
    league = pred.get(FantasyLeague, league_id)
    if league is None or not league.hb_division_id:
        return result

    hb = HBSession()
    # In-window FINAL game ids for this league's division.
    date_filter = ""
    params = {"did": league.hb_division_id}
    if league.season_starts_at:
        date_filter = " AND date >= :season_start"
        params["season_start"] = league.season_starts_at.date()
    # Filter on status_id (canonical): FINAL=3, FINAL_OT=4, FINAL_SO=5. The legacy
    # `status` strings are now uppercase (FINAL/FINAL_SO), so the old mixed-case
    # string IN (...) filter matches nothing — use status_id.
    game_rows = hb.execute(
        text(f"SELECT id FROM games WHERE division_id = :did "
             f"AND status_id IN (3, 4, 5)"
             f"{date_filter}"),
        params,
    ).fetchall()
    game_ids = [r.id for r in game_rows]
    if not game_ids:
        return result

    ids_sql = ",".join(str(int(g)) for g in game_ids)
    hid_sql = ",".join(str(int(h)) for h in hb_human_ids)

    # ── Skater: goals*3 + assists*2 + games_played*1 - penalties*0.5 ──────────
    # games_played = count of in-window games where the player appears on a roster.
    gp = {r.human_id: int(r.n) for r in hb.execute(text(
        f"SELECT human_id, COUNT(DISTINCT game_id) n FROM game_rosters "
        f"WHERE game_id IN ({ids_sql}) AND human_id IN ({hid_sql}) GROUP BY human_id")).fetchall()}
    goals = {}
    assists = {}
    for r in hb.execute(text(
        f"SELECT goal_scorer_id, assist_1_id, assist_2_id FROM goals WHERE game_id IN ({ids_sql})")).fetchall():
        if r.goal_scorer_id in result:
            goals[r.goal_scorer_id] = goals.get(r.goal_scorer_id, 0) + 1
        for a in (r.assist_1_id, r.assist_2_id):
            if a in result:
                assists[a] = assists.get(a, 0) + 1
    penalties = {r.penalized_player_id: int(r.n) for r in hb.execute(text(
        f"SELECT penalized_player_id, COUNT(*) n FROM penalties "
        f"WHERE game_id IN ({ids_sql}) AND penalized_player_id IN ({hid_sql}) "
        f"GROUP BY penalized_player_id")).fetchall()}

    # ── Goalie win/shutout BONUSES: credited to whoever was in net that game ───
    # (score_game applies these from goalie_results regardless of roster role.)
    goalie_win = {h: 0 for h in hb_human_ids}
    goalie_so = {h: 0 for h in hb_human_ids}
    for r in hb.execute(text(
        f"SELECT home_goalie_id, visitor_goalie_id, home_final_score, visitor_final_score "
        f"FROM games WHERE id IN ({ids_sql})")).fetchall():
        if r.home_final_score is None or r.visitor_final_score is None:
            continue
        h, v = r.home_final_score, r.visitor_final_score
        if r.home_goalie_id in result:
            if h > v: goalie_win[r.home_goalie_id] += 1
            if v == 0: goalie_so[r.home_goalie_id] += 1
        if r.visitor_goalie_id in result:
            if v > h: goalie_win[r.visitor_goalie_id] += 1
            if h == 0: goalie_so[r.visitor_goalie_id] += 1

    # ── Ref: games officiated * REF_GAME_PTS ──────────────────────────────────
    # Matches the (now-fixed) score_game ref logic: refs are on
    # games.referee_1_id / referee_2_id; scored on games officiated only (no
    # per-ref penalty/GM data source).
    ref_games: dict[int, int] = {}
    for r in hb.execute(text(
        f"SELECT referee_1_id, referee_2_id FROM games WHERE id IN ({ids_sql})")).fetchall():
        for rid in (r.referee_1_id, r.referee_2_id):
            if rid in result:
                ref_games[rid] = ref_games.get(rid, 0) + 1

    # Each value mirrors score_game exactly for a player of that roster role:
    #   points = goals*3 + assists*2 + games_played*perGameMult + penalties*-0.5
    #            + goalie_win_bonus + shutout_bonus
    # where games_played = count of in-window games the player is in game_rosters
    # (same for skater & goalie roles), perGameMult is 1 (skater) or 3 (goalie),
    # and win/shutout bonuses are credited to whoever was in net (any role).
    for h in hb_human_ids:
        common = (goals.get(h, 0) * GOAL_PTS + assists.get(h, 0) * ASSIST_PTS
                  + penalties.get(h, 0) * PENALTY_PTS
                  + goalie_win.get(h, 0) * GOALIE_WIN_PTS
                  + goalie_so.get(h, 0) * SHUTOUT_BONUS)
        g_played = gp.get(h, 0)
        result[h]["skater"] = round(common + g_played * GAME_PLAYED_PTS, 1)
        result[h]["goalie"] = round(common + g_played * GOALIE_GAME_PLAYED_PTS, 1)
        result[h]["ref"] = round(ref_games.get(h, 0) * REF_GAME_PTS, 1)
    return result


def backfill_scoring_after_trade(league_id: int) -> int:
    """
    Re-score every already-scored game in a league so that a newly-acquired
    player (who was NOT on any roster when the games were originally scored, e.g.
    a free agent picked up in a trade) gets their fantasy_game_scores rows
    created for the first time.

    score_game() only records rows for players CURRENTLY on a roster. Reattributing
    existing rows on a trade therefore does nothing for a player who never had rows.
    Re-running score_game for the league's finalized games fixes that: it upserts
    (idempotent) for players who already have rows, and creates rows for the newly
    rostered player. Returns the number of games re-scored.
    """
    pred = PredSession()
    scored_game_ids = [
        r.game_id
        for r in pred.execute(
            text("SELECT DISTINCT game_id FROM fantasy_game_scores "
                 "WHERE league_id = :lid AND is_provisional = FALSE"),
            {"lid": league_id},
        ).fetchall()
    ]
    for gid in scored_game_ids:
        try:
            score_game(league_id, gid)
        except Exception as e:
            logger.warning("[fantasy] backfill score_game(%d, %d) failed: %s", league_id, gid, e)
    logger.info("[fantasy] backfill_scoring_after_trade league=%d rescored=%d games",
                league_id, len(scored_game_ids))
    return len(scored_game_ids)


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

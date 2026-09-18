"""
fantasy_pool_service — builds the eligible player pool for a fantasy league.

Each human gets ONE entry with boolean flags: is_skater, is_goalie, is_ref.
Role-specific stats and fantasy points are stored per-role.
This handles multi-role players (e.g. someone who skates AND goalies AND refs).

The pool is seeded from ONE "draft season" (normally the last completed season,
which has rich stats). Players who never appeared in that season but have already
played at least one game in a NEWER season at the same level are merged in on top
and flagged `is_new_this_season` — otherwise a league that forms a couple of weeks
into a new season could never draft its newcomers.
"""

from sqlalchemy import select, func

from app.db import HBSession
from hockey_blast_common_lib.game_status import FINAL_STATUS_IDS

# Rough roster size of a real beer-league team. Used to cap the draftable skater
# pool: the pool is built from LAST season's stats and always over-counts, because
# players who have since left the league still have stats. teams * this is a much
# better estimate of how many skaters will actually take the ice this season.
SKATERS_PER_TEAM = 15


def suggest_max_pool_skaters(total_skaters: int, teams_this_season: int | None) -> int:
    """
    Default cap on the draftable skater pool: teams * SKATERS_PER_TEAM, never more
    than the pool actually holds. With no team count known, the raw pool stands.
    """
    if not teams_this_season or teams_this_season <= 0:
        return total_skaters
    return min(total_skaters, teams_this_season * SKATERS_PER_TEAM)


def roster_skaters_for(draftable_skaters: int, manager_count: int) -> int:
    """
    Skaters per team for `manager_count` managers sharing `draftable_skaters`.

    The single definition of the auto-adjust rule — used both by build_draft_queue
    when it writes the real roster at draft open, and by the league endpoint to
    project that number while the league is still forming, so the two can't drift.
    """
    if manager_count <= 0:
        return 1
    return max(1, min(10, draftable_skaters // manager_count))


def cap_skater_pool(total_skaters: int, max_pool_skaters: int | None) -> int:
    """Effective skater count every roster calculation must be sized against."""
    if not max_pool_skaters or max_pool_skaters <= 0:
        return total_skaters
    return min(total_skaters, int(max_pool_skaters))


def get_player_pool(
    level_id: int,
    org_id: int = 1,
    league_id: int = None,
    season_id: int = None,
    min_games: int = 1,
    include_new_players: bool = True,
) -> dict:
    """
    Returns the eligible player pool for a fantasy league at the given HB level.

    Scoring:
      Skater:  fantasy_points = (goals*3) + (assists*2) + (gp*1) - (penalties*0.5)
      Goalie:  fantasy_points = gp*3 + save_pct*5*gp
      Ref:     fantasy_points = games_reffed*4 + penalties_given*0.5 + gm_given*2

    Returns unified player list — each entry has is_skater/is_goalie/is_ref flags
    and role-specific stats. Sublists (skaters/goalies/refs) are derived from it.

    include_new_players: also merge in humans who have played/reffed at least one
    game in a season NEWER than the resolved draft season. They carry
    is_new_this_season=True and their current-season stats (min_games is not
    applied to them — one game is the whole point).
    """
    from hockey_blast_common_lib.stats_models import (
        DivisionStatsSkater,
        DivisionStatsGoalie,
        DivisionStatsReferee,
    )
    from hockey_blast_common_lib.models import Human, Division, Season
    from hockey_blast_common_lib.utils import get_non_human_ids

    hb = HBSession()
    non_human_ids = get_non_human_ids(hb)
    try:
        min_games = max(1, int(min_games))
    except (TypeError, ValueError):
        min_games = 1

    # ── Resolve season ────────────────────────────────────────────────────────
    from hockey_blast_common_lib.models import Season as HBSeason
    season_filter = [Division.level_id == level_id, Division.org_id == org_id]
    if league_id is not None:
        season_filter.append(
            Division.season_id.in_(
                select(HBSeason.id).where(HBSeason.league_id == league_id, HBSeason.org_id == org_id)
            )
        )

    from hockey_blast_common_lib.models import Game

    def _completed_games(sid):
        div_ids = hb.execute(
            select(Division.id).where(
                Division.level_id == level_id,
                Division.org_id == org_id,
                Division.season_id == sid,
            )
        ).scalars().all()
        if not div_ids:
            return 0
        return hb.execute(
            select(func.count(Game.id)).where(
                Game.division_id.in_(div_ids),
                Game.status_id.in_(FINAL_STATUS_IDS),
            )
        ).scalar() or 0

    if season_id is None:
        # Smart season resolution:
        # 1. Get the two most recent seasons with any divisions at this level
        # 2. Count completed (Final) games for each
        # 3. If the previous season has >= 2x more completed games than the latest,
        #    use the previous one (latest season just started, sparse stats)
        # 4. Otherwise use the latest season with any completed games
        # 5. Fall back to newest season if none have games
        candidate_seasons = hb.execute(
            select(Division.season_id)
            .where(*season_filter)
            .distinct()
            .order_by(Division.season_id.desc())
        ).scalars().all()

        if len(candidate_seasons) >= 2:
            latest_sid = candidate_seasons[0]
            prev_sid = candidate_seasons[1]
            latest_games = _completed_games(latest_sid)
            prev_games = _completed_games(prev_sid)
            # If previous season is 2x richer in completed games, use it
            if prev_games >= 2 * max(latest_games, 1):
                season_id = prev_sid
            elif latest_games > 0:
                season_id = latest_sid
            elif prev_games > 0:
                season_id = prev_sid
            else:
                season_id = latest_sid  # neither has games, use latest
        elif candidate_seasons:
            # Only one season — use it regardless
            season_id = candidate_seasons[0]
        # season_id stays None if no candidates at all

    # Resolve season name for display
    _resolved_season_name = None
    _last_game_date = None
    if season_id is not None:
        from hockey_blast_common_lib.models import Season as _Season
        _season_obj = hb.execute(select(_Season).where(_Season.id == season_id)).scalar_one_or_none()
        if _season_obj:
            _resolved_season_name = getattr(_season_obj, 'season_name', None) or f"Season {season_id}"
        # Find the latest scheduled game date in this season/level
        _div_ids_for_date = hb.execute(
            select(Division.id).where(
                Division.level_id == level_id,
                Division.org_id == org_id,
                Division.season_id == season_id,
            )
        ).scalars().all()
        if _div_ids_for_date:
            from hockey_blast_common_lib.models import Game as _Game
            _max_date = hb.execute(
                select(func.max(_Game.date)).where(
                    _Game.division_id.in_(_div_ids_for_date)
                )
            ).scalar()
            if _max_date:
                _last_game_date = _max_date.isoformat() if hasattr(_max_date, 'isoformat') else str(_max_date)

    div_ids_stmt = select(Division.id).where(
        Division.level_id == level_id,
        Division.org_id == org_id,
        Division.season_id == season_id,
    )

    # ── Newer seasons (already under way) ─────────────────────────────────────
    # Anyone who has skated/tended/reffed at least once in a season newer than the
    # draft season is draftable too, even though last season's stats don't know them.
    new_season_id = None
    _new_season_name = None
    if include_new_players and season_id is not None:
        newer_seasons = hb.execute(
            select(Division.season_id)
            .where(*season_filter, Division.season_id > season_id)
            .distinct()
            .order_by(Division.season_id.desc())
        ).scalars().all()
        # The newest season that has actually been played is "this season". Anything
        # older than it but newer than the draft season is a gap we don't draft from.
        for sid in newer_seasons:
            if _completed_games(sid) > 0:
                new_season_id = sid
                break
        if new_season_id is not None:
            _newest = hb.execute(
                select(Season).where(Season.id == new_season_id)
            ).scalar_one_or_none()
            if _newest:
                _new_season_name = getattr(_newest, 'season_name', None) or f"Season {new_season_id}"

    new_div_ids_stmt = None
    if new_season_id is not None:
        new_div_ids_stmt = select(Division.id).where(
            Division.level_id == level_id,
            Division.org_id == org_id,
            Division.season_id == new_season_id,
        )

    # ── Unified player dict keyed by human_id ─────────────────────────────────
    players: dict[int, dict] = {}

    def _base_entry(human_id, first_name, last_name, middle_name=None):
        return {
            "hb_human_id": human_id,
            "first_name": first_name,
            "middle_name": middle_name,
            "last_name": last_name,
            # Role flags
            "is_skater": False,
            "is_goalie": False,
            "is_ref": False,
            # True only for players merged in from a newer (already started) season
            "is_new_this_season": False,
            # Skater stats
            "games_played": 0,
            "goals": 0,
            "assists": 0,
            "points": 0,
            "penalties": 0,
            "fantasy_points_skater": 0.0,
            "fantasy_ppg": 0.0,
            # Goalie stats
            "goalie_games": 0,
            "goals_allowed": 0,
            "goals_against_avg": 0.0,
            "save_percentage": 0.0,
            "fantasy_points_goalie": 0.0,
            # Ref stats
            "games_reffed": 0,
            "penalties_given": 0,
            "gm_given": 0,
            "fantasy_points_ref": 0.0,
            # Primary fantasy_points — set per-role at access time, default to best role
            "fantasy_points": 0.0,
        }

    def _collect(div_stmt, gp_min: int, *, new_players_only: bool) -> None:
        """
        Fill `players` from the divisions selected by div_stmt.

        new_players_only=True skips humans already in the pool, so the draft-season
        entry (the richer, canonical one) always wins and only true newcomers are
        added — flagged is_new_this_season.
        """

        def _entry(human_id, first_name, last_name, middle_name):
            if new_players_only and human_id not in players:
                p = players.setdefault(
                    human_id, _base_entry(human_id, first_name, last_name, middle_name)
                )
                p["is_new_this_season"] = True
                return p
            if new_players_only and not players[human_id]["is_new_this_season"]:
                return None  # already known from the draft season — leave it alone
            return players.setdefault(
                human_id, _base_entry(human_id, first_name, last_name, middle_name)
            )

        # ── Skaters ───────────────────────────────────────────────────────────
        skater_stmt = (
            select(
                DivisionStatsSkater.human_id,
                Human.first_name, Human.middle_name, Human.last_name,
                func.sum(DivisionStatsSkater.games_played).label("games_played"),
                func.sum(DivisionStatsSkater.goals).label("goals"),
                func.sum(DivisionStatsSkater.assists).label("assists"),
                func.sum(DivisionStatsSkater.points).label("points"),
                func.sum(DivisionStatsSkater.penalties).label("penalties"),
            )
            .join(Human, Human.id == DivisionStatsSkater.human_id)
            .where(DivisionStatsSkater.division_id.in_(div_stmt))
            .where(DivisionStatsSkater.human_id.not_in(non_human_ids) if non_human_ids else True)
            .group_by(DivisionStatsSkater.human_id, Human.first_name, Human.middle_name, Human.last_name)
            .having(func.sum(DivisionStatsSkater.games_played) >= gp_min)
        )
        for row in hb.execute(skater_stmt).all():
            p = _entry(row.human_id, row.first_name, row.last_name, row.middle_name)
            if p is None:
                continue
            gp = row.games_played or 1
            goals = row.goals or 0
            assists = row.assists or 0
            penalties = row.penalties or 0
            fp = (goals * 3) + (assists * 2) + (gp * 1) - (penalties * 0.5)
            p["is_skater"] = True
            p["games_played"] = row.games_played
            p["goals"] = goals
            p["assists"] = assists
            p["points"] = row.points or (goals + assists)
            p["penalties"] = penalties
            p["fantasy_points_skater"] = round(fp, 2)
            p["fantasy_ppg"] = round(fp / gp, 3) if gp > 0 else 0.0

        # ── Goalies ───────────────────────────────────────────────────────────
        goalie_stmt = (
            select(
                DivisionStatsGoalie.human_id,
                Human.first_name, Human.middle_name, Human.last_name,
                func.sum(DivisionStatsGoalie.games_played).label("games_played"),
                func.sum(DivisionStatsGoalie.goals_allowed).label("goals_allowed"),
                func.avg(DivisionStatsGoalie.goals_allowed_per_game).label("goals_against_avg"),
                func.avg(DivisionStatsGoalie.save_percentage).label("save_percentage"),
            )
            .join(Human, Human.id == DivisionStatsGoalie.human_id)
            .where(DivisionStatsGoalie.division_id.in_(div_stmt))
            .where(DivisionStatsGoalie.human_id.not_in(non_human_ids) if non_human_ids else True)
            .group_by(DivisionStatsGoalie.human_id, Human.first_name, Human.middle_name, Human.last_name)
            .having(func.sum(DivisionStatsGoalie.games_played) >= gp_min)
        )
        for row in hb.execute(goalie_stmt).all():
            p = _entry(row.human_id, row.first_name, row.last_name, row.middle_name)
            if p is None:
                continue
            gp = row.games_played or 1
            save_pct = float(row.save_percentage or 0)
            fp = float(gp) * 3.0 + (save_pct * 5.0 * gp)
            p["is_goalie"] = True
            p["goalie_games"] = row.games_played
            p["goals_allowed"] = int(row.goals_allowed or 0)
            p["goals_against_avg"] = round(float(row.goals_against_avg or 0), 3)
            p["save_percentage"] = round(save_pct, 3)
            p["fantasy_points_goalie"] = round(fp, 2)

        # ── Refs ──────────────────────────────────────────────────────────────
        ref_stmt = (
            select(
                DivisionStatsReferee.human_id,
                Human.first_name, Human.middle_name, Human.last_name,
                func.sum(DivisionStatsReferee.games_reffed).label("games_reffed"),
                func.sum(DivisionStatsReferee.penalties_given).label("penalties_given"),
                func.sum(DivisionStatsReferee.gm_given).label("gm_given"),
            )
            .join(Human, Human.id == DivisionStatsReferee.human_id)
            .where(DivisionStatsReferee.division_id.in_(div_stmt))
            .where(DivisionStatsReferee.human_id.not_in(non_human_ids) if non_human_ids else True)
            .group_by(DivisionStatsReferee.human_id, Human.first_name, Human.middle_name, Human.last_name)
            .having(func.sum(DivisionStatsReferee.games_reffed) >= gp_min)
        )
        for row in hb.execute(ref_stmt).all():
            p = _entry(row.human_id, row.first_name, row.last_name, row.middle_name)
            if p is None:
                continue
            gr = int(row.games_reffed or 0)
            pg = int(row.penalties_given or 0)
            gm = int(row.gm_given or 0)
            # Must track fantasy_scoring_service REF_* constants — the board should
            # rank refs by what they will actually be paid.
            fp = gr * 4.0 + pg * 0.5 + gm * 2.0
            p["is_ref"] = True
            p["games_reffed"] = gr
            p["penalties_given"] = pg
            p["gm_given"] = gm
            p["fantasy_points_ref"] = round(fp, 2)

    # Draft season first — it owns every human it knows about.
    _collect(div_ids_stmt, min_games, new_players_only=False)

    # Then newcomers from the season(s) already under way. One game is enough:
    # min_games is a "prove it over last season" filter and must not hide them.
    _new_player_count = 0
    if new_div_ids_stmt is not None:
        _before = set(players)
        _collect(new_div_ids_stmt, 1, new_players_only=True)
        _new_player_count = len(set(players) - _before)

    # ── Set primary fantasy_points = best role ────────────────────────────────
    for p in players.values():
        p["fantasy_points"] = max(
            p["fantasy_points_skater"],
            p["fantasy_points_goalie"],
            p["fantasy_points_ref"],
        )

    player_list = list(players.values())

    # ── Derived sublists (for backward compat + frontend tabs) ────────────────
    skaters = sorted(
        [p for p in player_list if p["is_skater"]],
        key=lambda p: p["fantasy_points_skater"], reverse=True
    )
    goalies = sorted(
        [p for p in player_list if p["is_goalie"]],
        key=lambda p: p["fantasy_points_goalie"], reverse=True
    )
    refs = sorted(
        [p for p in player_list if p["is_ref"]],
        key=lambda p: p["fantasy_points_ref"], reverse=True
    )

    # ── Roster sizing ─────────────────────────────────────────────────────────
    pool_size = len(skaters)
    usable = int(pool_size * 0.7)
    roster_skaters = 5
    for r in range(10, 4, -1):
        if usable // r >= 4:
            roster_skaters = r
            break
    max_managers = min(12, usable // roster_skaters) if roster_skaters > 0 else 4
    max_managers = max(2, max_managers)

    # ── How many skaters will actually play this season ───────────────────────
    # Count the teams registered in the newest season at this level/league that
    # has any teams at all, and cap the pool at teams * SKATERS_PER_TEAM.
    from hockey_blast_common_lib.models import TeamDivision

    _teams_this_season = None
    _teams_season_id = None
    try:
        team_rows = hb.execute(
            select(Division.season_id, func.count(func.distinct(TeamDivision.team_id)))
            .select_from(Division)
            .join(TeamDivision, TeamDivision.division_id == Division.id)
            .where(*season_filter)
            .group_by(Division.season_id)
            .order_by(Division.season_id.desc())
        ).all()
        for sid, n_teams in team_rows:
            if n_teams and n_teams > 0:
                _teams_season_id = sid
                _teams_this_season = int(n_teams)
                break
    except Exception:
        _teams_this_season = None

    _max_pool_skaters = suggest_max_pool_skaters(pool_size, _teams_this_season)

    return {
        "players": player_list,   # unified list with all flags
        "skaters": skaters,       # is_skater=True, sorted by skater FP
        "goalies": goalies,       # is_goalie=True, sorted by goalie FP
        "refs": refs,             # is_ref=True, sorted by ref FP
        "roster_skaters": roster_skaters,
        "max_managers": max_managers,
        "teams_this_season": _teams_this_season,
        "teams_season_id": _teams_season_id,
        "max_pool_skaters": _max_pool_skaters,
        "resolved_season_id": season_id,
        "resolved_season_name": _resolved_season_name,
        "last_game_date": _last_game_date,
        "new_player_season_id": new_season_id,
        "new_player_season_name": _new_season_name,
        "new_player_count": _new_player_count,
    }

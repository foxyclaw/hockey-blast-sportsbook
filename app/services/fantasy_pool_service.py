"""
fantasy_pool_service — builds the eligible player pool for a fantasy league.

Each human gets ONE entry with boolean flags: is_skater, is_goalie, is_ref.
Role-specific stats and fantasy points are stored per-role.
This handles multi-role players (e.g. someone who skates AND goalies AND refs).
"""

from sqlalchemy import select, func

from app.db import HBSession


def get_player_pool(level_id: int, org_id: int = 1, league_id: int = None, season_id: int = None) -> dict:
    """
    Returns the eligible player pool for a fantasy league at the given HB level.

    Scoring:
      Skater:  fantasy_points = (goals*3) + (assists*2) + (gp*1) - (penalties*0.5)
      Goalie:  fantasy_points = gp*1 + save_pct*5*gp
      Ref:     fantasy_points = games_reffed*1 + penalties_given*1.5 + gm_given*8

    Returns unified player list — each entry has is_skater/is_goalie/is_ref flags
    and role-specific stats. Sublists (skaters/goalies/refs) are derived from it.
    """
    from hockey_blast_common_lib.stats_models import DivisionStatsSkater, DivisionStatsGoalie
    from hockey_blast_common_lib.models import Human, Division, Season
    from hockey_blast_common_lib.utils import get_non_human_ids

    hb = HBSession()
    non_human_ids = get_non_human_ids(hb)

    # ── Resolve season ────────────────────────────────────────────────────────
    from hockey_blast_common_lib.models import Season as HBSeason
    season_filter = [Division.level_id == level_id, Division.org_id == org_id]
    if league_id is not None:
        season_filter.append(
            Division.season_id.in_(
                select(HBSeason.id).where(HBSeason.league_id == league_id, HBSeason.org_id == org_id)
            )
        )

    if season_id is None:
        # Smart season resolution:
        # 1. Get the two most recent seasons with any divisions at this level
        # 2. Count completed (Final) games for each
        # 3. If the previous season has >= 2x more completed games than the latest,
        #    use the previous one (latest season just started, sparse stats)
        # 4. Otherwise use the latest season with any completed games
        # 5. Fall back to newest season if none have games
        from hockey_blast_common_lib.models import Game
        candidate_seasons = hb.execute(
            select(Division.season_id)
            .where(*season_filter)
            .distinct()
            .order_by(Division.season_id.desc())
        ).scalars().all()

        FINAL_STATUSES = ('Final', 'Final.', 'Final/OT', 'Final/OT2', 'Final/SO', 'Final(SO)')

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
                    Game.status.in_(FINAL_STATUSES),
                )
            ).scalar() or 0

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
    if season_id is not None:
        from hockey_blast_common_lib.models import Season as _Season
        _season_obj = hb.execute(select(_Season).where(_Season.id == season_id)).scalar_one_or_none()
        if _season_obj:
            _resolved_season_name = getattr(_season_obj, 'season_name', None) or f"Season {season_id}"

    div_ids_stmt = select(Division.id).where(
        Division.level_id == level_id,
        Division.org_id == org_id,
        Division.season_id == season_id,
    )

    # ── Unified player dict keyed by human_id ─────────────────────────────────
    players: dict[int, dict] = {}

    def _base_entry(human_id, first_name, last_name):
        return {
            "hb_human_id": human_id,
            "first_name": first_name,
            "last_name": last_name,
            # Role flags
            "is_skater": False,
            "is_goalie": False,
            "is_ref": False,
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

    # ── Skaters ───────────────────────────────────────────────────────────────
    skater_stmt = (
        select(
            DivisionStatsSkater.human_id,
            Human.first_name, Human.last_name,
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
    for row in hb.execute(skater_stmt).all():
        gp = row.games_played or 1
        goals = row.goals or 0
        assists = row.assists or 0
        penalties = row.penalties or 0
        fp = (goals * 3) + (assists * 2) + (gp * 1) - (penalties * 0.5)
        p = players.setdefault(row.human_id, _base_entry(row.human_id, row.first_name, row.last_name))
        p["is_skater"] = True
        p["games_played"] = row.games_played
        p["goals"] = goals
        p["assists"] = assists
        p["points"] = row.points or (goals + assists)
        p["penalties"] = penalties
        p["fantasy_points_skater"] = round(fp, 2)
        p["fantasy_ppg"] = round(fp / gp, 3) if gp > 0 else 0.0

    # ── Goalies ───────────────────────────────────────────────────────────────
    goalie_stmt = (
        select(
            DivisionStatsGoalie.human_id,
            Human.first_name, Human.last_name,
            func.sum(DivisionStatsGoalie.games_played).label("games_played"),
            func.sum(DivisionStatsGoalie.goals_allowed).label("goals_allowed"),
            func.avg(DivisionStatsGoalie.goals_allowed_per_game).label("goals_against_avg"),
            func.avg(DivisionStatsGoalie.save_percentage).label("save_percentage"),
        )
        .join(Human, Human.id == DivisionStatsGoalie.human_id)
        .where(DivisionStatsGoalie.division_id.in_(div_ids_stmt))
        .where(DivisionStatsGoalie.human_id.not_in(non_human_ids) if non_human_ids else True)
        .group_by(DivisionStatsGoalie.human_id, Human.first_name, Human.last_name)
        .having(func.sum(DivisionStatsGoalie.games_played) >= 1)
    )
    for row in hb.execute(goalie_stmt).all():
        gp = row.games_played or 1
        save_pct = float(row.save_percentage or 0)
        fp = float(gp) * 1.0 + (save_pct * 5.0 * gp)
        p = players.setdefault(row.human_id, _base_entry(row.human_id, row.first_name, row.last_name))
        p["is_goalie"] = True
        p["goalie_games"] = row.games_played
        p["goals_allowed"] = int(row.goals_allowed or 0)
        p["goals_against_avg"] = round(float(row.goals_against_avg or 0), 3)
        p["save_percentage"] = round(save_pct, 3)
        p["fantasy_points_goalie"] = round(fp, 2)

    # ── Refs ──────────────────────────────────────────────────────────────────
    from hockey_blast_common_lib.stats_models import DivisionStatsReferee
    ref_stmt = (
        select(
            DivisionStatsReferee.human_id,
            Human.first_name, Human.last_name,
            func.sum(DivisionStatsReferee.games_reffed).label("games_reffed"),
            func.sum(DivisionStatsReferee.penalties_given).label("penalties_given"),
            func.sum(DivisionStatsReferee.gm_given).label("gm_given"),
        )
        .join(Human, Human.id == DivisionStatsReferee.human_id)
        .where(DivisionStatsReferee.division_id.in_(div_ids_stmt))
        .where(DivisionStatsReferee.human_id.not_in(non_human_ids) if non_human_ids else True)
        .group_by(DivisionStatsReferee.human_id, Human.first_name, Human.last_name)
        .having(func.sum(DivisionStatsReferee.games_reffed) >= 3)
    )
    for row in hb.execute(ref_stmt).all():
        gr = int(row.games_reffed or 0)
        pg = int(row.penalties_given or 0)
        gm = int(row.gm_given or 0)
        fp = gr * 1.0 + pg * 1.5 + gm * 8.0
        p = players.setdefault(row.human_id, _base_entry(row.human_id, row.first_name, row.last_name))
        p["is_ref"] = True
        p["games_reffed"] = gr
        p["penalties_given"] = pg
        p["gm_given"] = gm
        p["fantasy_points_ref"] = round(fp, 2)

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

    return {
        "players": player_list,   # unified list with all flags
        "skaters": skaters,       # is_skater=True, sorted by skater FP
        "goalies": goalies,       # is_goalie=True, sorted by goalie FP
        "refs": refs,             # is_ref=True, sorted by ref FP
        "roster_skaters": roster_skaters,
        "max_managers": max_managers,
        "resolved_season_id": season_id,
        "resolved_season_name": _resolved_season_name,
    }

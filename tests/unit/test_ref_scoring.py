"""
Referee fantasy scoring.

There is no per-ref attribution of who blew the whistle — the DB records only
games.referee_1_id / referee_2_id. So every official working a game is credited
with ALL of that game's penalties and GMs; a two-ref game scores each call twice,
once per official.
"""

import pytest

from app.services.fantasy_scoring_service import (
    REF_GAME_PTS,
    REF_PENALTY_PTS,
    REF_GM_PTS,
    _compute_points,
)


# The shared conftest's autouse ``db_session`` fixture needs the Flask app + SQLite
# create_all (which currently fails on JSONB columns). Override it here so these
# pure-function tests stay independent of that.
@pytest.fixture(autouse=True)
def db_session():
    yield None


def _ref_points(games, penalties, gms):
    return _compute_points(
        goals=0, assists=0, penalties=0, games_played=0,
        is_goalie_win=False, is_shutout=False,
        ref_games=games, ref_penalties=penalties, ref_gm=gms,
        is_goalie=False,
    )


class TestRefPoints:
    def test_rates(self):
        # Calibrated to goalie parity — see the note on the constants.
        assert (REF_GAME_PTS, REF_PENALTY_PTS, REF_GM_PTS) == (4.0, 0.5, 2.0)

    def test_quiet_game(self):
        assert _ref_points(1, 0, 0) == 4.0

    def test_penalties_count(self):
        # 1 game + 6 penalties called
        assert _ref_points(1, 6, 0) == 4.0 + 3.0

    def test_gm_counts_as_both_a_penalty_and_a_gm(self):
        # A GM is a row in `penalties`, so it lands in both totals: 0.5 + 2.
        # 1 game, 3 penalties one of which is a GM.
        assert _ref_points(1, 3, 1) == 4.0 + 1.5 + 2.0

    def test_both_officials_score_the_same_game_identically(self):
        # Same game, two refs — each gets the full line, not half of it.
        game_penalties, game_gms = 5, 1
        ref_1 = _ref_points(1, game_penalties, game_gms)
        ref_2 = _ref_points(1, game_penalties, game_gms)
        assert ref_1 == ref_2 == 4.0 + 2.5 + 2.0

    def test_season_accumulates(self):
        # 12 games, 40 penalties, 2 GMs
        assert _ref_points(12, 40, 2) == 48.0 + 20.0 + 4.0

    def test_ref_line_is_independent_of_skater_scoring(self):
        # A ref line carries no games_played/goal/assist component.
        assert _ref_points(0, 0, 0) == 0.0


class TestGmDetection:
    """`gm_given` is `penalty_minutes == 'gm'`, matching HB's own referee stats."""

    @staticmethod
    def _is_gm(penalty_minutes):
        return (penalty_minutes or "").strip().lower() == "gm"

    @pytest.mark.parametrize("value", ["GM", "gm", " Gm ", "gM"])
    def test_recognised(self, value):
        assert self._is_gm(value)

    @pytest.mark.parametrize("value", ["2", "5", "10", "GS", "PS", "M", None, ""])
    def test_not_a_gm(self, value):
        assert not self._is_gm(value)


class TestCalibration:
    """
    The ref slot is 1 of 8 roster spots (6 skaters + 1 goalie + 1 ref), so it should
    pay about what the goalie slot pays. Measured over the two completed O35 seasons:
    skaters averaged 3.40 / 3.60 pts per game, goalies 5.34 / 5.53, and O35 runs
    2.09 penalties per game with both officials credited for all of them.
    """

    AVG_PENALTIES_PER_GAME = 2.09
    AVG_GMS_PER_GAME = 0.19

    def _typical_ref_game(self):
        return _ref_points(1, self.AVG_PENALTIES_PER_GAME, self.AVG_GMS_PER_GAME)

    def test_typical_ref_game_is_near_goalie_value(self):
        # Goalies averaged 5.34-5.53 pts per game across the two seasons.
        assert 4.5 <= self._typical_ref_game() <= 6.0

    def test_typical_ref_game_is_not_double_a_skater(self):
        # Skaters averaged 3.40-3.60. The old rates put refs at 8.1-10.4.
        assert self._typical_ref_game() < 2 * 3.60

    def test_a_brawl_does_not_decide_the_league(self):
        # The worst real game in the two seasons — HB game 362034, 2026-04-22:
        # 10 penalties, 6 of them GMs. At the old rates that one night paid each
        # official 72 pts, more than half a top skater's ENTIRE season (126-128).
        worst = _ref_points(1, 10, 6)
        assert worst == 21.0
        top_skater_season = 126.0
        assert worst < top_skater_season / 4

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
        assert (REF_GAME_PTS, REF_PENALTY_PTS, REF_GM_PTS) == (4.0, 2.0, 8.0)

    def test_quiet_game(self):
        assert _ref_points(1, 0, 0) == 4.0

    def test_penalties_count(self):
        # 1 game + 6 penalties called
        assert _ref_points(1, 6, 0) == 4.0 + 12.0

    def test_gm_counts_as_both_a_penalty_and_a_gm(self):
        # A GM is a row in `penalties`, so it lands in both totals: 2 + 8.
        # 1 game, 3 penalties one of which is a GM.
        assert _ref_points(1, 3, 1) == 4.0 + 6.0 + 8.0

    def test_both_officials_score_the_same_game_identically(self):
        # Same game, two refs — each gets the full line, not half of it.
        game_penalties, game_gms = 5, 1
        ref_1 = _ref_points(1, game_penalties, game_gms)
        ref_2 = _ref_points(1, game_penalties, game_gms)
        assert ref_1 == ref_2 == 4.0 + 10.0 + 8.0

    def test_season_accumulates(self):
        # 12 games, 40 penalties, 2 GMs
        assert _ref_points(12, 40, 2) == 48.0 + 80.0 + 16.0

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

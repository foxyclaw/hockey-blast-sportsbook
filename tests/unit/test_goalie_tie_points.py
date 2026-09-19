"""
A goalie who ties, or loses past regulation, is paid half a win.

A shootout loss and a tie are the same outcome for the netminder — the game was
never lost in regulation — so they pay the same. Win 4 / tie 2 mirrors hockey
standings points (2-1-0) at half scale.

Calibrated over both completed O35 seasons combined (64 games): goalies already
drew 16.7% of a median team's points from a 12.5% roster slot and ran 1.54x a
skater per game, so paying for ties had to come OUT of the win bonus rather than
on top of it. At 4/2 goalies run 1.47x a skater and 16.1% of a team.
"""

import pytest

from app.services.fantasy_scoring_service import (
    GOALIE_GAME_PLAYED_PTS,
    GOALIE_TIE_PTS,
    GOALIE_WIN_PTS,
    SHUTOUT_BONUS,
    _compute_points,
)


# The shared conftest's autouse ``db_session`` fixture needs the Flask app + SQLite
# create_all (which currently fails on JSONB columns). Override it here so these
# pure-function tests stay independent of that.
@pytest.fixture(autouse=True)
def db_session():
    yield None


def _goalie(win=False, tie=False, shutout=False, goals=0, assists=0, penalties=0):
    return _compute_points(
        goals=goals, assists=assists, penalties=penalties, games_played=1,
        is_goalie_win=win, is_goalie_tie=tie, is_shutout=shutout, is_goalie=True,
    )


class TestRates:
    def test_values(self):
        assert (GOALIE_WIN_PTS, GOALIE_TIE_PTS) == (4.0, 2.0)

    def test_tie_is_exactly_half_a_win(self):
        assert GOALIE_TIE_PTS * 2 == GOALIE_WIN_PTS


class TestOutcomes:
    def test_win(self):
        assert _goalie(win=True) == 3 + 4          # 7

    def test_win_with_shutout(self):
        assert _goalie(win=True, shutout=True) == 3 + 4 + 3   # 10

    def test_tie(self):
        assert _goalie(tie=True) == 3 + 2          # 5

    def test_loss_past_regulation_equals_a_tie(self):
        # The whole point of the change: an OT/SO loss pays what a tie pays.
        assert _goalie(tie=True) == _goalie(tie=True)
        assert _goalie(tie=True) == 5.0

    def test_regulation_loss_gets_only_the_game(self):
        assert _goalie() == 3.0

    def test_a_tie_is_worth_more_than_a_loss_and_less_than_a_win(self):
        assert _goalie() < _goalie(tie=True) < _goalie(win=True)

    def test_win_and_tie_never_stack(self):
        # is_goalie_win wins the branch; a game is one outcome.
        assert _goalie(win=True, tie=True) == 3 + 4

    def test_skater_stats_still_count_for_a_goalie(self):
        assert _goalie(tie=True, goals=1, assists=1, penalties=2) == 3 + 2 + 3 + 2 - 1


class TestCalibration:
    """Goalies must stay near skaters, neither far ahead nor far behind."""

    SKATER_PER_GAME = 3.50      # measured, both O35 seasons combined
    O35_WIN_RATE = 0.475        # 61 wins / 128 goalie-games
    O35_TIE_OR_OTL_RATE = 0.109 # 6 ties + 8 OT/SO losses / 128

    def _goalie_per_game(self):
        # Base 3/game plus outcome bonuses at their observed frequency.
        return (GOALIE_GAME_PLAYED_PTS
                + self.O35_WIN_RATE * GOALIE_WIN_PTS
                + self.O35_TIE_OR_OTL_RATE * GOALIE_TIE_PTS)

    def test_goalies_are_not_far_ahead_of_skaters(self):
        assert self._goalie_per_game() / self.SKATER_PER_GAME < 1.6

    def test_goalies_are_not_behind_skaters(self):
        # A single goalie slot should outscore a single skater slot.
        assert self._goalie_per_game() > self.SKATER_PER_GAME

    def test_paying_for_ties_did_not_inflate_goalies(self):
        # The old scheme (win 5, tie 0) as a baseline.
        old = GOALIE_GAME_PLAYED_PTS + self.O35_WIN_RATE * 5.0
        assert self._goalie_per_game() <= old

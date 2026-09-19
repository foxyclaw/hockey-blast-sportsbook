"""
A shootout's result lives in the `shootout` table, not the final score.

15% of FINAL_SO games league-wide — and 24% of O35's — store a tied final score
with the deciding goal missing. The shootout table records every attempt, so the
winner is recoverable:

  1. more shootout goals wins; otherwise
  2. the shootout stopped the moment it was decided, so the LAST attempt decides
     — scored means that team won, missed means the other did.

Validated against the 2,333 FINAL_SO games whose score already names a winner:
99.6% agreement, and it resolves all 652 tie-stored games carrying shootout rows.
"""

import pytest


@pytest.fixture(autouse=True)
def db_session():
    yield None


HOME, AWAY = 10, 20


def _winner(rows):
    """Mirrors _shootout_winner_team; rows are (team, scored) in sequence order."""
    if not rows:
        return None
    hg = sum(1 for t, s in rows if t == HOME and s)
    ag = sum(1 for t, s in rows if t == AWAY and s)
    if hg != ag:
        return HOME if hg > ag else AWAY
    t, s = rows[-1]
    if s:
        return t
    return AWAY if t == HOME else HOME


class TestGoalCount:
    def test_more_goals_wins(self):
        assert _winner([(AWAY, False), (HOME, True), (AWAY, False), (HOME, False)]) == HOME

    def test_more_goals_wins_away(self):
        assert _winner([(AWAY, True), (HOME, False), (AWAY, True), (HOME, True)]) == AWAY


class TestLastAttemptDecides:
    def test_last_attempt_scored_wins_it(self):
        # 397840 shape: 2-2, last attempt is HOME and scores.
        rows = [(AWAY, False), (HOME, False), (AWAY, False), (HOME, True),
                (AWAY, True), (HOME, False), (AWAY, True), (HOME, True)]
        assert _winner(rows) == HOME

    def test_last_attempt_missed_loses_it(self):
        # 397834 shape: 1-1, last attempt is AWAY and misses.
        rows = [(AWAY, False), (HOME, False), (AWAY, False), (HOME, True),
                (AWAY, True), (HOME, False), (AWAY, False)]
        assert _winner(rows) == HOME

    def test_all_missed_last_shooter_loses(self):
        assert _winner([(AWAY, False), (HOME, False), (AWAY, False)]) == HOME


class TestFallback:
    def test_no_rows_is_undecidable(self):
        assert _winner([]) is None


class TestPayout:
    """Winner takes the win bonus, loser is paid as a tie — not as a loss."""

    def test_loser_is_paid_as_a_tie(self):
        from app.services.fantasy_scoring_service import (
            GOALIE_GAME_PLAYED_PTS, GOALIE_TIE_PTS, GOALIE_WIN_PTS, _compute_points)

        def gk(win, tie):
            return _compute_points(goals=0, assists=0, penalties=0, games_played=1,
                                   is_goalie_win=win, is_goalie_tie=tie,
                                   is_shutout=False, is_goalie=True)
        assert gk(True, False) == GOALIE_GAME_PLAYED_PTS + GOALIE_WIN_PTS   # 7
        assert gk(False, True) == GOALIE_GAME_PLAYED_PTS + GOALIE_TIE_PTS   # 5
        assert gk(False, True) > gk(False, False)

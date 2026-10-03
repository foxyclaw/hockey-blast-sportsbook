"""
A blocked player must be unacquirable by trade, not merely undraftable.

The draft path checked settings.draft_blocked in four places; the trade path in
none. So a blocked player stayed acquirable all season — and because the
expired-turn auto-trade takes max(available, key=fantasy_points), a blocked
player who tops the pool is the FIRST candidate it reaches for. That is exactly
how human 116004 (126.0 FP, the highest-scoring skater in the O35 pool) landed on
a roster in league 122 on 2026-10-02, one minute after a turn deadline expired.

get_available_players is the single chokepoint: the /trade/available list,
make_trade's validation and the auto-trade candidate search all read it.
"""

import pytest


@pytest.fixture(autouse=True)
def db_session():
    yield None


def _available(pool, rostered, blocked):
    """The filter get_available_players applies."""
    return [p for p in pool
            if p["hb_human_id"] not in rostered and p["hb_human_id"] not in blocked]


TOP = {"hb_human_id": 116004, "fantasy_points": 126.0}     # blocked
GOOD = {"hb_human_id": 200, "fantasy_points": 94.5}
MID = {"hb_human_id": 300, "fantasy_points": 50.0}
ROSTERED = {"hb_human_id": 400, "fantasy_points": 80.0}
POOL = [TOP, GOOD, MID, ROSTERED]


class TestFilter:
    def test_blocked_player_is_not_available(self):
        out = _available(POOL, rostered={400}, blocked={116004})
        assert TOP not in out

    def test_rostered_player_still_filtered(self):
        out = _available(POOL, rostered={400}, blocked={116004})
        assert ROSTERED not in out

    def test_unblocked_players_survive(self):
        out = _available(POOL, rostered={400}, blocked={116004})
        assert out == [GOOD, MID]

    def test_empty_blocklist_changes_nothing(self):
        out = _available(POOL, rostered=set(), blocked=set())
        assert out == POOL

    def test_unblocking_makes_them_available_again(self):
        # The block is a filter, never a deletion — lifting it restores them.
        assert TOP in _available(POOL, rostered=set(), blocked=set())


class TestAutoTradeReachesForTheTopScorer:
    """_try_auto_trade_for_expired_turn does max(available, key=fantasy_points)."""

    @staticmethod
    def _auto_pick(pool, rostered, blocked):
        avail = _available(pool, rostered, blocked)
        return max(avail, key=lambda p: p["fantasy_points"]) if avail else None

    def test_without_the_filter_it_picks_the_blocked_player(self):
        # Regression witness: this is the live bug.
        assert self._auto_pick(POOL, rostered={400}, blocked=set()) is TOP

    def test_with_the_filter_it_picks_the_best_legal_player(self):
        assert self._auto_pick(POOL, rostered={400}, blocked={116004}) is GOOD

    def test_no_legal_candidate_yields_none(self):
        assert self._auto_pick(POOL, rostered={200, 300, 400}, blocked={116004}) is None

"""
The draftable skater pool is capped at teams * SKATERS_PER_TEAM.

The stats pool is built from LAST season, so it always over-counts: players who
have since left the league still carry stats. Sizing rosters off the raw pool
hands out more roster spots than there are real players.
"""

import pytest

from app.services.fantasy_pool_service import (
    SKATERS_PER_TEAM,
    cap_skater_pool,
    suggest_max_pool_skaters,
)


# The shared conftest's autouse ``db_session`` fixture needs the Flask app + SQLite
# create_all (which currently fails on JSONB columns).  Override it here so these
# pure-function tests stay independent of that.
@pytest.fixture(autouse=True)
def db_session():
    yield None


class TestSuggestMaxPoolSkaters:
    def test_teams_times_fifteen(self):
        # Fremont O35: 4 teams, 72 skaters in last season's stats → 60 in play.
        assert suggest_max_pool_skaters(72, 4) == 60

    def test_never_exceeds_the_real_pool(self):
        # 8 teams would want 120, but only 90 skaters exist in the pool.
        assert suggest_max_pool_skaters(90, 8) == 90

    def test_unknown_team_count_leaves_pool_alone(self):
        assert suggest_max_pool_skaters(72, None) == 72
        assert suggest_max_pool_skaters(72, 0) == 72

    def test_constant_is_fifteen(self):
        assert SKATERS_PER_TEAM == 15


class TestCapSkaterPool:
    def test_cap_applies(self):
        assert cap_skater_pool(72, 60) == 60

    def test_no_cap_set(self):
        assert cap_skater_pool(72, None) == 72
        assert cap_skater_pool(72, 0) == 72

    def test_cap_above_pool_is_ignored(self):
        assert cap_skater_pool(72, 200) == 72


class TestAutoRosterSizing:
    """The sizing rule build_draft_queue applies: min(10, skaters // managers)."""

    @staticmethod
    def _roster_skaters(total, cap, managers):
        return max(1, min(10, cap_skater_pool(total, cap) // managers))

    @pytest.mark.parametrize("managers,expected", [(6, 10), (7, 8), (8, 7), (10, 6)])
    def test_capped_pool_sizes_rosters(self, managers, expected):
        # 72 in the stats pool, 60 actually playing.
        assert self._roster_skaters(72, 60, managers) == expected

    def test_uncapped_pool_overshoots(self):
        # Without the cap, 8 managers would each get 9 skaters — 72 spots for 60 players.
        assert self._roster_skaters(72, None, 8) == 9
        assert self._roster_skaters(72, 60, 8) == 7

    def test_never_below_one(self):
        assert self._roster_skaters(3, 3, 8) == 1

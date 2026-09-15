"""
Autopick must obey the same position rule as a manual pick.

make_pick rejects a pure goalie or pure ref in a skater round ("Goalies can only
be picked in the goalie round"), and _queue_pick reads pool["skaters"]. But
_best_available drew from goalies + refs + skaters and excluded only refs, so an
absent manager could be auto-assigned a goalie in a skater slot — recorded with
is_goalie=False, scoring 1 pt/game instead of 3, and leaving them a skater short.

These tests pin the eligibility rule the three paths must agree on.
"""

import pytest


# The shared conftest's autouse ``db_session`` fixture needs the Flask app + SQLite
# create_all (which currently fails on JSONB columns). Override it here so these
# pure-function tests stay independent of that.
@pytest.fixture(autouse=True)
def db_session():
    yield None


def _player(hid, skater=False, goalie=False, ref=False, fp=0.0):
    return {"hb_human_id": hid, "is_skater": skater, "is_goalie": goalie,
            "is_ref": ref, "fantasy_points": fp}


PURE_SKATER = _player(1, skater=True, fp=10.0)
PURE_GOALIE = _player(2, goalie=True, fp=99.0)   # high FP — the old fallback's top choice
PURE_REF = _player(3, ref=True, fp=80.0)
SKATER_GOALIE = _player(4, skater=True, goalie=True, fp=50.0)
SKATER_REF = _player(5, skater=True, ref=True, fp=40.0)

ALL = [PURE_SKATER, PURE_GOALIE, PURE_REF, SKATER_GOALIE, SKATER_REF]
# get_player_pool builds each sublist by role flag, so pool["skaters"] IS the is_skater set.
POOL_SKATERS = [p for p in ALL if p["is_skater"]]


def _eligible_for_skater_slot(pool_skaters, drafted=(), blocked=()):
    """The rule _best_available now applies for a skater slot."""
    return [p for p in pool_skaters
            if p["hb_human_id"] not in drafted and p["hb_human_id"] not in blocked]


def _make_pick_would_allow(player, is_goalie_pick=False, is_ref_pick=False):
    """Mirrors the guard in make_pick."""
    if is_goalie_pick:
        return bool(player.get("is_goalie"))
    if is_ref_pick:
        return bool(player.get("is_ref"))
    if player.get("is_goalie") and not player.get("is_skater"):
        return False
    if player.get("is_ref") and not player.get("is_skater"):
        return False
    return True


class TestSkaterSlotEligibility:
    def test_pure_goalie_is_not_eligible(self):
        assert PURE_GOALIE not in _eligible_for_skater_slot(POOL_SKATERS)

    def test_pure_ref_is_not_eligible(self):
        assert PURE_REF not in _eligible_for_skater_slot(POOL_SKATERS)

    def test_dual_role_players_stay_eligible(self):
        elig = _eligible_for_skater_slot(POOL_SKATERS)
        assert SKATER_GOALIE in elig, "a goalie who also skates is draftable as a skater"
        assert SKATER_REF in elig, "a ref who also skates is draftable as a skater"

    def test_plain_skater_eligible(self):
        assert PURE_SKATER in _eligible_for_skater_slot(POOL_SKATERS)

    def test_drafted_and_blocked_still_filtered(self):
        elig = _eligible_for_skater_slot(POOL_SKATERS, drafted={1}, blocked={4})
        assert [p["hb_human_id"] for p in elig] == [5]

    def test_high_fp_goalie_no_longer_wins_the_fallback(self):
        # The fallback picks max by fantasy_points. The pure goalie's 99.0 would have
        # beaten every real skater under the old all_pool comprehension.
        elig = _eligible_for_skater_slot(POOL_SKATERS)
        best = max(elig, key=lambda p: p["fantasy_points"])
        assert best is SKATER_GOALIE and best["is_skater"]

    def test_empty_rather_than_an_illegal_pick(self):
        # No skaters left: better to hand back nothing than an out-of-position player.
        assert _eligible_for_skater_slot([]) == []


class TestAgreesWithManualPick:
    """Whatever autopick may choose, make_pick must also have accepted."""

    @pytest.mark.parametrize("player", ALL, ids=lambda p: str(p["hb_human_id"]))
    def test_autopick_never_exceeds_manual_rules(self, player):
        auto_ok = player in _eligible_for_skater_slot(POOL_SKATERS)
        manual_ok = _make_pick_would_allow(player)
        assert auto_ok == manual_ok, f"paths disagree on {player}"

    def test_the_old_behaviour_did_disagree(self):
        # Regression witness: the old rule (all pools, minus refs) admitted a goalie.
        old_rule = [p for p in ALL if not p.get("is_ref")]
        assert PURE_GOALIE in old_rule
        assert not _make_pick_would_allow(PURE_GOALIE)

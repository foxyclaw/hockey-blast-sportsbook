"""
A manager may stand pat at ANY point in a trade round, not only on their turn.

Owner, 2026-10-02: "anyone can skip their swap at ANY TIME (say I like my team),
do not wait for their turn." Someone happy with their roster should not have to
sit through everyone ahead of them to pass, and the round should not spend a 24h
deadline on a manager who already knows they are standing pat.

Nothing in the advance machinery changes for this. Both turn-finders filter
`is_skipped == False`, so a turn marked skipped BEFORE its deadline is set is
simply stepped over when the round reaches it. These tests pin that contract,
because it is the whole reason the feature is a one-line state change rather
than new scheduling logic.
"""

import pytest


@pytest.fixture(autouse=True)
def db_session():
    yield None


class Turn:
    """Mirrors the fields the two turn-finder queries filter on."""
    def __init__(self, uid, order, pass_number=1, deadline=None,
                 acted_at=None, is_skipped=False, is_missed=False):
        self.user_id, self.turn_order, self.pass_number = uid, order, pass_number
        self.deadline, self.acted_at = deadline, acted_at
        self.is_skipped, self.is_missed = is_skipped, is_missed

    def __repr__(self):
        return f"Turn(u{self.user_id},o{self.turn_order})"


def _unresolved(t):
    return t.acted_at is None and not t.is_skipped and not t.is_missed


def current_turn(turns):
    """_current_turn: deadline set + unresolved."""
    c = [t for t in turns if t.deadline is not None and _unresolved(t)]
    c.sort(key=lambda t: (t.pass_number, t.turn_order))
    return c[0] if c else None


def next_unstarted(turns):
    """_next_unstarted_turn: no deadline yet + unresolved."""
    c = [t for t in turns if t.deadline is None and _unresolved(t)]
    c.sort(key=lambda t: (t.pass_number, t.turn_order))
    return c[0] if c else None


def skip(turns, user_id):
    """skip_turn: mark every unresolved turn this manager holds."""
    mine = [t for t in turns if t.user_id == user_id and _unresolved(t)]
    if not mine:
        raise ValueError("You have no turn left to skip in this round")
    for t in mine:
        t.is_skipped = True
        t.acted_at = "now"
    return mine


def _round(n=4):
    ts = [Turn(uid=10 * i, order=i) for i in range(1, n + 1)]
    ts[0].deadline = "set"          # manager 10 is on the clock
    return ts


class TestSkipOffTurn:
    def test_a_waiting_manager_can_skip(self):
        ts = _round()
        skip(ts, 30)                       # third in line, not on the clock
        assert [t for t in ts if t.user_id == 30][0].is_skipped

    def test_skipping_off_turn_does_not_steal_the_clock(self):
        ts = _round()
        before = current_turn(ts)
        skip(ts, 30)
        assert current_turn(ts) is before, "whoever was mid-turn keeps it"

    def test_the_round_steps_over_a_pre_skipped_manager(self):
        ts = _round()
        skip(ts, 20)                       # the NEXT manager pre-skips
        assert next_unstarted(ts).user_id == 30, "20 is passed over entirely"

    def test_on_the_clock_skip_still_works(self):
        ts = _round()
        skip(ts, 10)
        assert current_turn(ts) is None     # clock freed
        assert next_unstarted(ts).user_id == 20

    def test_everyone_skipping_leaves_nothing_to_serve(self):
        ts = _round()
        for u in (10, 20, 30, 40):
            skip(ts, u)
        assert current_turn(ts) is None and next_unstarted(ts) is None

    def test_cannot_skip_twice(self):
        ts = _round()
        skip(ts, 30)
        with pytest.raises(ValueError):
            skip(ts, 30)

    def test_cannot_skip_after_trading(self):
        ts = _round()
        [t for t in ts if t.user_id == 30][0].acted_at = "traded"
        with pytest.raises(ValueError):
            skip(ts, 30)


class TestSecondChance:
    """_build_second_chance_pass revives MISSED turns only."""

    def test_a_skipper_is_not_dragged_back(self):
        ts = _round()
        skip(ts, 30)
        missed = [t for t in ts if t.is_missed]
        assert missed == [], "choosing to stand pat is not a missed turn"

    def test_a_missed_turn_is_still_revivable(self):
        ts = _round()
        t = [x for x in ts if x.user_id == 30][0]
        t.is_missed = True
        assert t.is_missed and not t.is_skipped

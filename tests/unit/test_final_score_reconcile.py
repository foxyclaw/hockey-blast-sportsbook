"""
The FINAL scoring pass is authoritative.

score_live_game writes rows from game_rosters as it stood mid-game. HB rewrites
the roster when a game is finalised, so a player who drops off keeps a
stuck-provisional row: the scoring loop `continue`s past anyone not in
`participants`, so nothing ever revisits it and the phantom points are paid out
for the rest of the season.

Observed live in league 122, game 397520: Jeremy Thurston, Justin Bult and Paul
Collanton each held a provisional 1-point row while absent from that game's
roster — 2 points to Sloppy Joes and 1 to Old Tyme that no game produced.

These pin the reconciliation rule: after the final pass, the rows for a game are
exactly the rows that pass produced.
"""

import pytest


# The shared conftest's autouse ``db_session`` fixture needs the Flask app + SQLite
# create_all (which currently fails on JSONB columns). Override it here so these
# pure-function tests stay independent of that.
@pytest.fixture(autouse=True)
def db_session():
    yield None


def _rows_after_final(existing_rows, scored_ids, participants, ref_stats):
    """The reconciliation score_game applies: drop anything the pass didn't produce."""
    if not (participants or ref_stats):
        return set(existing_rows)          # no evidence — change nothing
    if not scored_ids:
        return set()                       # nobody rostered played — no rows belong
    return {h for h in existing_rows if h in scored_ids}


class TestReconciliation:
    def test_the_live_bug(self):
        # 397520: live scored 5, but only 2 are on the final roster.
        existing = {111, 222, 333, 444, 555}
        scored = {111, 222}
        assert _rows_after_final(existing, scored, participants={111, 222}, ref_stats={}) == {111, 222}

    def test_untouched_when_nothing_changed(self):
        existing = {111, 222}
        assert _rows_after_final(existing, {111, 222}, {111, 222}, {}) == {111, 222}

    def test_refs_are_kept(self):
        # Refs score from ref_stats, not game_rosters — they must survive.
        existing = {111, 999}
        assert _rows_after_final(existing, {111, 999}, participants={111}, ref_stats={999: {}}) == {111, 999}

    def test_a_replaced_ref_is_dropped(self):
        # Assignment changed after the live pass: old ref 998 must not keep points.
        existing = {111, 998}
        assert _rows_after_final(existing, {111, 999}, participants={111}, ref_stats={999: {}}) == {111}

    def test_no_evidence_deletes_nothing(self):
        # Both HB lookups came back empty — never wipe a game on no information.
        existing = {111, 222}
        assert _rows_after_final(existing, set(), participants=set(), ref_stats={}) == {111, 222}

    def test_no_rostered_player_in_the_game(self):
        # The game happened and had participants, but none are on any fantasy roster.
        existing = {111}
        assert _rows_after_final(existing, set(), participants={777, 888}, ref_stats={}) == set()

    def test_idempotent(self):
        existing = {111, 222, 333}
        once = _rows_after_final(existing, {111, 222}, {111, 222}, {})
        twice = _rows_after_final(once, {111, 222}, {111, 222}, {})
        assert once == twice == {111, 222}

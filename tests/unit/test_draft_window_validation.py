"""
Draft window validation.

A draft that is still running when the season starts silently loses games:
scoring only counts games on/after season_starts_at, so anything played while
managers are still picking never scores for anyone. That is a setup error, and
it can't be repaired after the fact — so it is refused at the door.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.blueprints.fantasy import parse_league_dt, validate_draft_window


# The shared conftest's autouse ``db_session`` fixture needs the Flask app + SQLite
# create_all (which currently fails on JSONB columns). Override it here so these
# pure-function tests stay independent of that.
@pytest.fixture(autouse=True)
def db_session():
    yield None


OPENS = datetime(2026, 9, 14, 19, 0, tzinfo=timezone.utc)


class TestValidateDraftWindow:
    def test_league_122_shape_is_valid(self):
        # opens 9/14 19:00, closes 9/16 19:30, season starts 9/16 20:00
        closes = datetime(2026, 9, 16, 19, 30, tzinfo=timezone.utc)
        season = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)
        assert validate_draft_window(OPENS, closes, season) is None

    def test_closes_after_season_start_is_rejected(self):
        closes = datetime(2026, 9, 16, 21, 0, tzinfo=timezone.utc)
        season = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)
        err = validate_draft_window(OPENS, closes, season)
        assert err and "on or before Season Starts" in err

    def test_closes_exactly_at_season_start_is_allowed(self):
        at = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)
        assert validate_draft_window(OPENS, at, at) is None

    def test_closes_before_opens_is_rejected(self):
        err = validate_draft_window(OPENS, OPENS - timedelta(hours=1), None)
        assert err and "after Draft Opens" in err

    def test_closes_equal_to_opens_is_rejected(self):
        err = validate_draft_window(OPENS, OPENS, None)
        assert err and "after Draft Opens" in err

    def test_opens_after_season_start_is_rejected(self):
        season = OPENS - timedelta(days=1)
        err = validate_draft_window(OPENS, OPENS + timedelta(hours=1), season)
        assert err is not None

    def test_missing_fields_are_not_second_guessed(self):
        # season_starts_at is optional; nothing to compare against.
        assert validate_draft_window(OPENS, OPENS + timedelta(days=2), None) is None
        assert validate_draft_window(None, OPENS + timedelta(days=2), None) is None
        assert validate_draft_window(None, None, None) is None


class TestParseLeagueDt:
    @pytest.mark.parametrize("raw", [
        "2026-09-16T19:30:00+00:00",
        "2026-09-16T19:30:00Z",
        "2026-09-16T19:30",
        "2026-09-16 19:30",
    ])
    def test_accepted_forms(self, raw):
        assert parse_league_dt(raw) is not None

    def test_date_only(self):
        assert parse_league_dt("2026-09-16").date() == datetime(2026, 9, 16).date()

    def test_passthrough_and_empty(self):
        assert parse_league_dt(OPENS) is OPENS
        assert parse_league_dt(None) is None
        assert parse_league_dt("") is None
        assert parse_league_dt("not a date") is None

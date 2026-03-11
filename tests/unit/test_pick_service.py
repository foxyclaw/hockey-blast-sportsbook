"""
Unit tests for pick_service — uses mocking to avoid HB DB dependency.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

from app.services.pick_service import (
    PickLockedError,
    InvalidTeamError,
    NotLeagueMemberError,
    compute_projected_points,
)
from app.models.pred_pick import PredPick
from app.models.pred_league import PredLeague, LeagueScope


class TestProjectedPoints:
    """Test compute_projected_points without needing a DB."""

    def _make_pick(self, confidence=1, skill_diff=None, is_upset=False):
        pick = MagicMock(spec=PredPick)
        pick.confidence = confidence
        pick.skill_differential = skill_diff
        pick.is_upset_pick = is_upset
        return pick

    def _make_league(self, base=10, upset=True, multiplier=True):
        league = MagicMock(spec=PredLeague)
        league.correct_pick_base_points = base
        league.upset_bonus_enabled = upset
        league.confidence_multiplier_enabled = multiplier
        return league

    def test_base_pick(self):
        pick = self._make_pick(confidence=1, skill_diff=0.0)
        league = self._make_league()
        result = compute_projected_points(pick, league)
        assert result["correct"] == 10
        assert result["wrong"] == 0

    def test_high_confidence_multiplier(self):
        pick = self._make_pick(confidence=3, skill_diff=0.0)
        league = self._make_league()
        result = compute_projected_points(pick, league)
        assert result["correct"] == 30

    def test_upset_bonus(self):
        pick = self._make_pick(confidence=1, skill_diff=25.0)
        league = self._make_league()
        result = compute_projected_points(pick, league)
        assert result["correct"] == 22  # 10 + 12 (floor(25*0.5))

    def test_full_upset_with_multiplier(self):
        pick = self._make_pick(confidence=3, skill_diff=25.0)
        league = self._make_league()
        result = compute_projected_points(pick, league)
        assert result["correct"] == 66

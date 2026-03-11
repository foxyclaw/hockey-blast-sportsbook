"""
Unit tests for the scoring math.
No DB, no HTTP — pure function tests.
"""

import pytest
from app.services.result_grader import compute_points, compute_upset_bonus


class TestComputeUpsetBonus:
    def test_no_bonus_for_favorite_pick(self):
        assert compute_upset_bonus(-10.0) == 0

    def test_no_bonus_for_even_matchup(self):
        assert compute_upset_bonus(0.0) == 0

    def test_bonus_for_mild_upset(self):
        # floor(10 * 0.5) = 5
        assert compute_upset_bonus(10.0) == 5

    def test_bonus_for_big_upset(self):
        # floor(30 * 0.5) = 15
        assert compute_upset_bonus(30.0) == 15

    def test_bonus_for_extreme_upset(self):
        # floor(50 * 0.5) = 25
        assert compute_upset_bonus(50.0) == 25

    def test_no_bonus_for_none(self):
        assert compute_upset_bonus(None) == 0

    def test_bonus_floors_fractional(self):
        # floor(25 * 0.5) = 12 (not 12.5)
        assert compute_upset_bonus(25.0) == 12


class TestComputePoints:
    def test_wrong_pick_always_zero(self):
        result = compute_points(
            is_correct=False,
            skill_differential=50.0,
            confidence=3,
        )
        assert result["total_points"] == 0

    def test_correct_pick_base(self):
        result = compute_points(
            is_correct=True,
            skill_differential=0.0,
            confidence=1,
        )
        assert result["base_points"] == 10
        assert result["upset_bonus_points"] == 0
        assert result["total_points"] == 10

    def test_correct_pick_with_confidence_multiplier(self):
        result = compute_points(
            is_correct=True,
            skill_differential=0.0,
            confidence=3,
        )
        assert result["total_points"] == 30  # 10 * 3

    def test_upset_bonus_applied(self):
        # skill_diff = +25 → floor(25 * 0.5) = 12 upset bonus
        result = compute_points(
            is_correct=True,
            skill_differential=25.0,
            confidence=1,
        )
        assert result["upset_bonus_points"] == 12
        assert result["pre_multiplier_points"] == 22
        assert result["total_points"] == 22

    def test_upset_bonus_with_multiplier(self):
        # From DESIGN.md example: Puck Bunnies (skill 55) vs Quacks (30)
        # skill_diff = 55 - 30 = 25, conf = 3x
        # base=10, upset=12, pre=22, total=66
        result = compute_points(
            is_correct=True,
            skill_differential=25.0,
            confidence=3,
        )
        assert result["base_points"] == 10
        assert result["upset_bonus_points"] == 12
        assert result["pre_multiplier_points"] == 22
        assert result["total_points"] == 66

    def test_upset_bonus_disabled(self):
        result = compute_points(
            is_correct=True,
            skill_differential=25.0,
            confidence=3,
            upset_bonus_enabled=False,
        )
        assert result["upset_bonus_points"] == 0
        assert result["total_points"] == 30  # 10 * 3 only

    def test_confidence_multiplier_disabled(self):
        result = compute_points(
            is_correct=True,
            skill_differential=0.0,
            confidence=3,
            confidence_multiplier_enabled=False,
        )
        # multiplier ignored → 10 * 1
        assert result["confidence_multiplier"] == 1
        assert result["total_points"] == 10

    def test_none_skill_differential_no_bonus(self):
        result = compute_points(
            is_correct=True,
            skill_differential=None,
            confidence=2,
        )
        assert result["upset_bonus_points"] == 0
        assert result["total_points"] == 20  # 10 * 2

    def test_scoring_table_from_design_doc(self):
        """Verify all rows in the DESIGN.md scoring table."""
        cases = [
            # (diff, conf, expected_total)
            (0, 1, 10),
            (0, 2, 20),
            (0, 3, 30),
            (10, 1, 15),
            (10, 3, 45),
            (30, 1, 25),
            (30, 3, 75),
            (50, 3, 105),
        ]
        for diff, conf, expected in cases:
            result = compute_points(is_correct=True, skill_differential=float(diff), confidence=conf)
            assert result["total_points"] == expected, (
                f"diff={diff}, conf={conf}: expected {expected}, got {result['total_points']}"
            )

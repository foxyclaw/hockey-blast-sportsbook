"""
Unit tests for paper-money (balance/wager) logic.

Tests:
  - PredUser starts with balance=1000
  - submit_pick validates wager range (1–500)
  - submit_pick raises INSUFFICIENT_BALANCE when wager > balance
  - _compute_balance_change: correct pick → positive balance change
  - _compute_balance_change: wrong pick → negative balance change
  - _compute_balance_change: voided game → zero change
  - multiplier = confidence + upset_bonus
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from app.models.pred_pick import PredPick
from app.models.pred_result import PredResult
from app.models.pred_user import PredUser
from app.services.result_grader import _compute_balance_change
from app.services.pick_service import PickError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — use MagicMock with spec so attribute access is controlled
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(balance=1000):
    user = MagicMock(spec=PredUser)
    user.id = 1
    user.auth0_sub = "test|123"
    user.display_name = "Test User"
    user.email = "test@example.com"
    user.avatar_url = None
    user.hb_human_id = None
    user.is_active = True
    user.balance = balance
    user.created_at = datetime.now(timezone.utc)
    user.last_login_at = None
    return user


def _make_pick(confidence=2, is_upset_pick=False, wager=None):
    pick = MagicMock(spec=PredPick)
    pick.id = 1
    pick.user_id = 1
    pick.league_id = 1
    pick.game_id = 100
    pick.picked_team_id = 10
    pick.home_team_id = 10
    pick.away_team_id = 20
    pick.confidence = confidence
    pick.is_upset_pick = is_upset_pick
    pick.wager = wager
    pick.is_locked = False
    pick.game_scheduled_start = datetime.now(timezone.utc)
    pick.skill_differential = 5.0 if is_upset_pick else -5.0
    return pick


def _make_result(is_correct=True, actual_winner=10, game_final_status="Final"):
    result = MagicMock(spec=PredResult)
    result.pick_id = 1
    result.is_correct = is_correct
    result.actual_winner_team_id = actual_winner
    result.game_final_status = game_final_status
    result.base_points = 10 if is_correct else 0
    result.upset_bonus_points = 0
    result.pre_multiplier_points = 10 if is_correct else 0
    result.confidence_multiplier = 2
    result.total_points = 20 if is_correct else 0
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PredUser balance field
# ─────────────────────────────────────────────────────────────────────────────

def test_pred_user_balance_field_exists():
    """PredUser model has a `balance` column."""
    cols = {c.key for c in PredUser.__table__.columns}
    assert "balance" in cols


def test_pred_user_balance_column_default():
    """balance column has server_default of 1000."""
    col = PredUser.__table__.columns["balance"]
    # server_default text should contain "1000"
    assert col.server_default is not None
    assert "1000" in str(col.server_default.arg)


# ─────────────────────────────────────────────────────────────────────────────
# PredPick wager field
# ─────────────────────────────────────────────────────────────────────────────

def test_pred_pick_wager_field_exists():
    """PredPick model has a `wager` column that is nullable."""
    cols = {c.key: c for c in PredPick.__table__.columns}
    assert "wager" in cols
    assert cols["wager"].nullable is True


# ─────────────────────────────────────────────────────────────────────────────
# PredResult balance_change field
# ─────────────────────────────────────────────────────────────────────────────

def test_pred_result_wager_and_balance_change_fields_exist():
    """PredResult model has `wager` and `balance_change` columns."""
    cols = {c.key for c in PredResult.__table__.columns}
    assert "wager" in cols
    assert "balance_change" in cols


# ─────────────────────────────────────────────────────────────────────────────
# _compute_balance_change
# ─────────────────────────────────────────────────────────────────────────────

def test_balance_change_no_wager():
    """No wager → balance_change = 0."""
    pick = _make_pick(wager=None, confidence=2, is_upset_pick=False)
    result = _make_result(is_correct=True)
    assert _compute_balance_change(pick, result) == 0


def test_balance_change_correct_pick_no_upset():
    """Correct, confidence=2, no upset → multiplier=2 → +100."""
    pick = _make_pick(wager=50, confidence=2, is_upset_pick=False)
    result = _make_result(is_correct=True, actual_winner=10, game_final_status="Final")
    change = _compute_balance_change(pick, result)
    assert change == 50 * 2  # multiplier = confidence(2) + upset_bonus(0)


def test_balance_change_correct_pick_with_upset():
    """Correct, confidence=2, is_upset_pick=True → multiplier=3 → +150."""
    pick = _make_pick(wager=50, confidence=2, is_upset_pick=True)
    result = _make_result(is_correct=True, actual_winner=10, game_final_status="Final")
    change = _compute_balance_change(pick, result)
    assert change == 50 * 3  # multiplier = confidence(2) + upset_bonus(1)


def test_balance_change_correct_pick_confidence_3_upset():
    """Confidence=3, upset → multiplier=4 → +200."""
    pick = _make_pick(wager=50, confidence=3, is_upset_pick=True)
    result = _make_result(is_correct=True, game_final_status="Final/OT")
    change = _compute_balance_change(pick, result)
    assert change == 50 * 4


def test_balance_change_wrong_pick():
    """Wrong pick → lose the wager."""
    pick = _make_pick(wager=100, confidence=3, is_upset_pick=False)
    result = _make_result(is_correct=False, actual_winner=20, game_final_status="Final")
    change = _compute_balance_change(pick, result)
    assert change == -100


def test_balance_change_voided_game():
    """Voided/forfeited game → balance refund (0 change)."""
    pick = _make_pick(wager=200, confidence=2, is_upset_pick=False)
    result = _make_result(is_correct=False, actual_winner=None, game_final_status="Forfeit")
    change = _compute_balance_change(pick, result)
    assert change == 0


def test_balance_change_canceled_game():
    """Canceled game → balance refund (0 change)."""
    pick = _make_pick(wager=150, confidence=1, is_upset_pick=False)
    result = _make_result(is_correct=False, actual_winner=None, game_final_status="CANCELED")
    change = _compute_balance_change(pick, result)
    assert change == 0


def test_balance_change_confidence_1_no_upset():
    """Confidence=1, no upset → multiplier=1 → +50."""
    pick = _make_pick(wager=50, confidence=1, is_upset_pick=False)
    result = _make_result(is_correct=True, game_final_status="Final/SO")
    change = _compute_balance_change(pick, result)
    assert change == 50


# ─────────────────────────────────────────────────────────────────────────────
# submit_pick wager validation
# ─────────────────────────────────────────────────────────────────────────────

_SKILL_PATCHES = {
    "validate_pick_window": lambda: None,
    "_assert_league_member": lambda: None,
    "_get_game_teams": (10, 20, datetime.now(timezone.utc)),
    "get_game_skill_snapshot": {"home_team_avg_skill": 50.0, "away_team_avg_skill": 60.0},
    "compute_pick_skill_fields": {
        "picked_team_avg_skill": 50.0,
        "opponent_avg_skill": 60.0,
        "skill_differential": -10.0,
        "is_upset_pick": False,
    },
}


def _patched_submit(user, wager, confidence=1, balance_check=True):
    """Helper to call submit_pick with all HB dependencies mocked."""
    from app.services.pick_service import submit_pick

    mock_session = MagicMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    with patch("app.services.pick_service.validate_pick_window"), \
         patch("app.services.pick_service._assert_league_member"), \
         patch("app.services.pick_service._get_game_teams",
               return_value=(10, 20, datetime.now(timezone.utc))), \
         patch("app.services.pick_service.get_game_skill_snapshot",
               return_value={"home_team_avg_skill": 50.0, "away_team_avg_skill": 60.0}), \
         patch("app.services.pick_service.compute_pick_skill_fields",
               return_value={
                   "picked_team_avg_skill": 50.0,
                   "opponent_avg_skill": 60.0,
                   "skill_differential": -10.0,
                   "is_upset_pick": False,
               }):
        return submit_pick(
            user=user,
            game_id=100,
            league_id=1,
            picked_team_id=10,
            confidence=confidence,
            pred_session=mock_session,
            wager=wager,
        )


def test_submit_pick_insufficient_balance():
    """Wager > balance raises INSUFFICIENT_BALANCE."""
    user = _make_user(balance=100)

    with pytest.raises(PickError) as exc_info:
        _patched_submit(user, wager=200)

    assert exc_info.value.code == "INSUFFICIENT_BALANCE"
    assert exc_info.value.http_status == 400


def test_submit_pick_invalid_wager_too_high():
    """Wager > 500 raises VALIDATION_ERROR."""
    user = _make_user(balance=9999)

    with pytest.raises(PickError) as exc_info:
        _patched_submit(user, wager=501)

    assert exc_info.value.code == "VALIDATION_ERROR"


def test_submit_pick_invalid_wager_zero():
    """Wager of 0 raises VALIDATION_ERROR."""
    user = _make_user(balance=9999)

    with pytest.raises(PickError) as exc_info:
        _patched_submit(user, wager=0)

    assert exc_info.value.code == "VALIDATION_ERROR"


def test_submit_pick_no_wager_allowed():
    """No wager (None) passes even with zero balance."""
    user = _make_user(balance=0)

    pick = _patched_submit(user, wager=None)
    assert pick.wager is None


def test_submit_pick_valid_wager_stored():
    """Valid wager is stored on the pick."""
    user = _make_user(balance=500)

    pick = _patched_submit(user, wager=250)
    assert pick.wager == 250


def test_submit_pick_wager_exactly_balance():
    """Wager exactly equal to balance is allowed."""
    user = _make_user(balance=300)

    pick = _patched_submit(user, wager=300)
    assert pick.wager == 300


def test_submit_pick_wager_max_500():
    """Wager of 500 (max) is allowed."""
    user = _make_user(balance=1000)

    pick = _patched_submit(user, wager=500)
    assert pick.wager == 500


def test_submit_pick_wager_min_1():
    """Wager of 1 (min) is allowed."""
    user = _make_user(balance=1000)

    pick = _patched_submit(user, wager=1)
    assert pick.wager == 1

"""
Pick lock checker — determines if a game is still pickable.

Lock conditions (any one makes a game unpickable):
  1. Game not found in hockey_blast DB
  2. Game status is not "Scheduled"
  3. game.live_time is not None (game is live)
  4. game.game_date_time - BUFFER <= now()  (game starts within buffer window)

BUFFER is configurable via PICK_LOCK_BUFFER_MINUTES env var (default: 0).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import HBSession


def _get_lock_buffer_minutes() -> int:
    """Return configured pick lock buffer in minutes."""
    try:
        from flask import current_app
        return current_app.config.get("PICK_LOCK_BUFFER_MINUTES", 0)
    except RuntimeError:
        return 0  # Outside app context (e.g. tests)


def _get_game(game_id: int):
    """
    Fetch a game from the hockey_blast DB.
    Returns the game ORM object or None.

    NOTE: This assumes hockey_blast_common_lib provides a Game model
    accessible via HBSession. If the model path differs, update this import.
    """
    try:
        from hockey_blast_common_lib.models import Game
        session = HBSession()
        stmt = select(Game).where(Game.id == game_id)
        return session.execute(stmt).scalar_one_or_none()
    except ImportError:
        # hockey_blast_common_lib not installed — used in tests with stubs
        return None


def is_game_pickable(game_id: int) -> tuple[bool, str]:
    """
    Check if a pick can be submitted (or modified) for this game.

    Returns:
        (True, "")           — pick is allowed
        (False, reason_str)  — pick is locked with human-readable reason
    """
    game = _get_game(game_id)

    if game is None:
        return False, "Game not found"

    # Check game status
    status = getattr(game, "status", None)
    if status != "Scheduled":
        return False, f"Game is not scheduled (status: {status!r})"

    # Check if game is live
    if getattr(game, "live_time", None) is not None:
        return False, "Game is currently live"

    # Check time window
    scheduled = getattr(game, "game_date_time", None)
    if scheduled is None:
        return False, "Game has no scheduled start time"

    # Make timezone-aware if naive
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)

    buffer = timedelta(minutes=_get_lock_buffer_minutes())
    lock_at = scheduled - buffer
    now = datetime.now(timezone.utc)

    if now >= lock_at:
        return False, "Pick window has closed (game has started)"

    return True, ""


def get_lock_deadline(game_id: int) -> datetime | None:
    """
    Return the datetime when picks lock for this game.
    = game.game_date_time - BUFFER

    Returns None if game not found.
    """
    game = _get_game(game_id)
    if game is None:
        return None

    scheduled = getattr(game, "game_date_time", None)
    if scheduled is None:
        return None

    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)

    buffer = timedelta(minutes=_get_lock_buffer_minutes())
    return scheduled - buffer

"""
Pick lock checker — determines if a game is still pickable.

Lock conditions (any one makes a game unpickable):
  1. Game not found in hockey_blast DB
  2. Game status is not "Scheduled"
  3. game.live_time is not None (game is live)
  4. game start datetime - BUFFER <= now()

NOTE: games table has separate `date` (date) and `time` (time) columns.
      We combine them into a UTC-naive datetime for comparison.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import HBSession


def _get_lock_buffer_minutes() -> int:
    try:
        from flask import current_app
        return current_app.config.get("PICK_LOCK_BUFFER_MINUTES", 0)
    except RuntimeError:
        return 0


def _game_start_dt(game) -> datetime | None:
    """Combine game.date + game.time into a timezone-aware datetime (Pacific)."""
    game_date = getattr(game, "date", None)
    game_time = getattr(game, "time", None)
    if game_date is None:
        return None
    if game_time is not None:
        dt = datetime.combine(game_date, game_time)
    else:
        dt = datetime(game_date.year, game_date.month, game_date.day, 0, 0, 0)
    # Games are in Pacific time — store as UTC-naive but compare with local time
    # Using naive datetime comparison (both sides will be naive or both aware)
    return dt


def _get_game(game_id: int):
    try:
        from hockey_blast_common_lib.models import Game
        session = HBSession()
        stmt = select(Game).where(Game.id == game_id)
        return session.execute(stmt).scalar_one_or_none()
    except ImportError:
        return None


def is_game_pickable(game_id: int) -> tuple[bool, str]:
    game = _get_game(game_id)

    if game is None:
        return False, "Game not found"

    status = getattr(game, "status", None)
    if status != "Scheduled":
        return False, f"Game is not scheduled (status: {status!r})"

    if getattr(game, "live_time", None) is not None:
        return False, "Game is currently live"

    scheduled = _game_start_dt(game)
    if scheduled is None:
        return False, "Game has no scheduled start time"

    buffer = timedelta(minutes=_get_lock_buffer_minutes())
    lock_at = scheduled - buffer
    now = datetime.now()  # naive local time to match game times

    if now >= lock_at:
        return False, "Pick window has closed (game has started)"

    return True, ""


def get_lock_deadline(game_id: int) -> datetime | None:
    game = _get_game(game_id)
    if game is None:
        return None

    scheduled = _game_start_dt(game)
    if scheduled is None:
        return None

    buffer = timedelta(minutes=_get_lock_buffer_minutes())
    return scheduled - buffer

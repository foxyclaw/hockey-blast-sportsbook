"""
Datetime utilities — TZ handling and formatting.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC datetime (always timezone-aware)."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """
    Ensure a datetime is timezone-aware (UTC).
    If naive, assumes UTC and adds tzinfo.
    Returns None if input is None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def isoformat_or_none(dt: datetime | None) -> str | None:
    """Return ISO 8601 string or None."""
    if dt is None:
        return None
    return ensure_utc(dt).isoformat()

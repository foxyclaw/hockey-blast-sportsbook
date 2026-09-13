"""
Small in-process TTL cache for rarely-changing reference rows (teams, divisions,
levels, organizations) that are read from the hockey_blast DB on every request.

Deliberately simple: a dict of key -> (expires_at, value), a lock, and a size
bound (oldest-inserted entries are evicted first).  Each gunicorn worker has its
own copy; that's fine for data that changes a few times per season.

Environment knobs (read when a cache is constructed, i.e. at import time):
    HB_REF_CACHE_DISABLED=1       — never store anything (use in tests)
    HB_REF_CACHE_TTL_SECONDS=600  — entry lifetime; 0 also disables
"""

import os
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

DEFAULT_TTL_SECONDS = 600.0  # 10 minutes
DEFAULT_MAX_SIZE = 5000


def _env_disabled() -> bool:
    return os.environ.get("HB_REF_CACHE_DISABLED", "").strip().lower() in ("1", "true", "yes")


def _env_ttl() -> float:
    raw = os.environ.get("HB_REF_CACHE_TTL_SECONDS")
    if raw is None or not raw.strip():
        return DEFAULT_TTL_SECONDS
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_TTL_SECONDS


class TTLCache:
    """Thread-safe {key: value} cache with a per-entry TTL and a max size."""

    def __init__(
        self,
        ttl_seconds: float | None = None,
        max_size: int = DEFAULT_MAX_SIZE,
        enabled: bool | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.ttl = _env_ttl() if ttl_seconds is None else float(ttl_seconds)
        self.max_size = max_size
        if enabled is None:
            enabled = not _env_disabled() and self.ttl > 0
        self.enabled = enabled
        self._clock = clock
        self._lock = threading.Lock()
        self._data: dict[Any, tuple[float, Any]] = {}

    def get_many(self, keys: Iterable[Any]) -> dict:
        """Return {key: value} for the keys that are cached and not expired."""
        if not self.enabled:
            return {}
        now = self._clock()
        found = {}
        with self._lock:
            for key in keys:
                entry = self._data.get(key)
                if entry is None:
                    continue
                expires_at, value = entry
                if expires_at <= now:
                    del self._data[key]
                    continue
                found[key] = value
        return found

    def get(self, key: Any, default: Any = None) -> Any:
        return self.get_many([key]).get(key, default)

    def set_many(self, items: dict) -> None:
        if not self.enabled or not items:
            return
        now = self._clock()
        expires_at = now + self.ttl
        with self._lock:
            for key, value in items.items():
                # Re-insert so refreshed keys move to the "newest" end for eviction.
                self._data.pop(key, None)
                self._data[key] = (expires_at, value)
            if len(self._data) > self.max_size:
                self._evict_locked(now)

    def set(self, key: Any, value: Any) -> None:
        self.set_many({key: value})

    def _evict_locked(self, now: float) -> None:
        expired = [k for k, (exp, _) in self._data.items() if exp <= now]
        for k in expired:
            del self._data[k]
        while len(self._data) > self.max_size:
            # dict preserves insertion order -> first key is the oldest
            self._data.pop(next(iter(self._data)))

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


def load_cached(cache: TTLCache, keys: Iterable[Any], loader: Callable[[list], dict]) -> dict:
    """
    Return {key: value} for ``keys`` (deduplicated, ``None`` skipped), serving from
    ``cache`` and calling ``loader(missing_keys)`` at most ONCE for the rest.

    Keys the loader does not return are stored as ``None`` (negative cache) so a
    dangling id does not cost a query on every request.  If the loader raises,
    nothing is cached and the exception propagates.
    """
    wanted = [k for k in dict.fromkeys(keys) if k is not None]
    if not wanted:
        return {}
    found = cache.get_many(wanted)
    missing = [k for k in wanted if k not in found]
    if missing:
        fresh = loader(missing)
        loaded = {k: fresh.get(k) for k in missing}
        cache.set_many(loaded)
        found.update(loaded)
    return found

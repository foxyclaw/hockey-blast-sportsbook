"""
Unit tests for app.services.ref_cache — no DB, no Flask app.
"""

import pytest

from app.services.ref_cache import TTLCache, load_cached


# The shared conftest's autouse ``db_session`` fixture needs the Flask app + SQLite
# create_all (which currently fails on JSONB columns).  Override it here so these
# tests stay independent of that.
@pytest.fixture
def db_session():
    yield None


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _cache(ttl=600, max_size=5000, enabled=True):
    clock = FakeClock()
    return TTLCache(ttl_seconds=ttl, max_size=max_size, enabled=enabled, clock=clock), clock


class TestTTLCache:
    def test_set_and_get(self):
        cache, _ = _cache()
        cache.set_many({1: "a", 2: "b"})
        assert cache.get_many([1, 2, 3]) == {1: "a", 2: "b"}
        assert cache.get(2) == "b"
        assert cache.get(3, "dflt") == "dflt"
        assert len(cache) == 2

    def test_entries_expire_after_ttl(self):
        cache, clock = _cache(ttl=600)
        cache.set(1, "a")
        clock.advance(599)
        assert cache.get_many([1]) == {1: "a"}
        clock.advance(1)  # exactly at expiry -> gone
        assert cache.get_many([1]) == {}
        assert len(cache) == 0  # expired entry was dropped on read

    def test_refresh_extends_lifetime(self):
        cache, clock = _cache(ttl=100)
        cache.set(1, "a")
        clock.advance(80)
        cache.set(1, "a2")
        clock.advance(80)
        assert cache.get(1) == "a2"

    def test_none_values_are_cached(self):
        cache, _ = _cache()
        cache.set_many({7: None})
        assert cache.get_many([7]) == {7: None}

    def test_disabled_cache_stores_nothing(self):
        cache, _ = _cache(enabled=False)
        cache.set_many({1: "a"})
        assert cache.get_many([1]) == {}
        assert len(cache) == 0

    def test_zero_ttl_disables(self):
        cache = TTLCache(ttl_seconds=0)
        assert cache.enabled is False

    def test_env_disable(self, monkeypatch):
        monkeypatch.setenv("HB_REF_CACHE_DISABLED", "1")
        assert TTLCache(ttl_seconds=600).enabled is False
        monkeypatch.setenv("HB_REF_CACHE_DISABLED", "0")
        assert TTLCache(ttl_seconds=600).enabled is True

    def test_env_ttl(self, monkeypatch):
        monkeypatch.delenv("HB_REF_CACHE_DISABLED", raising=False)
        monkeypatch.setenv("HB_REF_CACHE_TTL_SECONDS", "42")
        assert TTLCache().ttl == 42.0
        monkeypatch.setenv("HB_REF_CACHE_TTL_SECONDS", "not-a-number")
        assert TTLCache().ttl == 600.0

    def test_size_bound_evicts_oldest_first(self):
        cache, _ = _cache(max_size=3)
        cache.set_many({1: "a", 2: "b", 3: "c"})
        cache.set(4, "d")
        assert len(cache) == 3
        assert cache.get_many([1, 2, 3, 4]) == {2: "b", 3: "c", 4: "d"}

    def test_size_bound_drops_expired_before_live(self):
        cache, clock = _cache(ttl=100, max_size=3)
        cache.set_many({1: "a", 2: "b"})
        clock.advance(150)  # 1, 2 expired but still resident
        cache.set_many({3: "c", 4: "d"})  # over bound -> expired go first
        assert cache.get_many([1, 2, 3, 4]) == {3: "c", 4: "d"}

    def test_clear(self):
        cache, _ = _cache()
        cache.set(1, "a")
        cache.clear()
        assert cache.get_many([1]) == {}


class TestLoadCached:
    def test_loader_called_once_with_misses_only(self):
        cache, _ = _cache()
        cache.set(1, "cached")
        calls = []

        def loader(ids):
            calls.append(list(ids))
            return {i: f"v{i}" for i in ids}

        out = load_cached(cache, [1, 2, 3, 2, None, 1], loader)
        assert out == {1: "cached", 2: "v2", 3: "v3"}
        assert calls == [[2, 3]]  # deduped, cached + None skipped
        # second call is fully served from cache
        assert load_cached(cache, [3, 2], loader) == {3: "v3", 2: "v2"}
        assert calls == [[2, 3]]

    def test_missing_ids_are_negative_cached(self):
        cache, _ = _cache()
        calls = []

        def loader(ids):
            calls.append(list(ids))
            return {}  # nothing exists

        assert load_cached(cache, [9], loader) == {9: None}
        assert load_cached(cache, [9], loader) == {9: None}
        assert calls == [[9]]

    def test_empty_keys_skip_loader(self):
        cache, _ = _cache()
        called = []
        assert load_cached(cache, [None, None], lambda ids: called.append(ids) or {}) == {}
        assert called == []

    def test_loader_error_caches_nothing(self):
        cache, _ = _cache()

        def loader(ids):
            raise RuntimeError("db down")

        with pytest.raises(RuntimeError):
            load_cached(cache, [1], loader)
        assert len(cache) == 0

    def test_disabled_cache_always_calls_loader(self):
        cache, _ = _cache(enabled=False)
        calls = []

        def loader(ids):
            calls.append(list(ids))
            return {i: i for i in ids}

        load_cached(cache, [1], loader)
        load_cached(cache, [1], loader)
        assert calls == [[1], [1]]

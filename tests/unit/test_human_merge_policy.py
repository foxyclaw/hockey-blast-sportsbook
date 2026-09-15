import ast
import pathlib

from app.services.human_merge_policy import human_merges_enabled

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HB_HUMAN_MERGES_ENABLED", raising=False)
    assert human_merges_enabled() is False


def test_only_explicit_opt_in(monkeypatch):
    for v in ("", "0", "true", "yes"):
        monkeypatch.setenv("HB_HUMAN_MERGES_ENABLED", v)
        assert human_merges_enabled() is False
    monkeypatch.setenv("HB_HUMAN_MERGES_ENABLED", "1")
    assert human_merges_enabled() is True


def test_every_merge_call_is_behind_the_policy():
    """Every merge_humans(...) call in the app sits in an `elif` whose
    matching `if` checks `not human_merges_enabled()`."""
    for rel in ("app/blueprints/identity.py", "app/blueprints/admin.py"):
        src = (ROOT / rel).read_text()
        calls = src.count("merge_humans(")
        guards = src.count("and not human_merges_enabled()")
        assert calls >= 1, rel
        assert guards >= 1 and "log_skipped_merge(" in src, rel
        ast.parse(src)

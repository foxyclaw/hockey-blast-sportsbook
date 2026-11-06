"""
A league imported into the social site (hockey-blast.com) is read-only here.

FANTASY_DESIGN.md §6.3: the import sets ``fantasy_leagues.migrated_at`` as its
last step. From then on every fantasy write answers 409
``{"error": "league_migrated", "url": <migrated_to_url>}`` and every fantasy
job skips the league. These tests pin:
  * reject_if_migrated() — None for a live league, the 409 shape for a moved one
  * every league-selecting job query filters ``migrated_at IS NULL``
    (statements are captured from a fake session and compiled for Postgres; no DB)
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy.dialects import postgresql

from app.utils.response import reject_if_migrated


# The shared conftest's autouse ``db_session`` needs SQLite create_all, which fails
# on JSONB columns. Override it so these tests stay DB-free.
@pytest.fixture
def db_session():
    yield None


URL = "https://hockey-blast.com/fantasy/123"


# ── reject_if_migrated ───────────────────────────────────────────────────────

class TestRejectIfMigrated:
    def test_live_league_passes(self):
        league = SimpleNamespace(migrated_at=None, migrated_to_url=None)
        assert reject_if_migrated(league) is None

    def test_missing_league_passes_through(self):
        # The handler's own 404 path still owns a missing league.
        assert reject_if_migrated(None) is None

    def test_migrated_league_is_409_with_url(self):
        league = SimpleNamespace(migrated_at=datetime.now(timezone.utc), migrated_to_url=URL)
        with Flask(__name__).app_context():
            resp, status = reject_if_migrated(league)
            body = resp.get_json()
        assert status == 409
        assert body["error"] == "league_migrated"
        assert body["url"] == URL

    def test_migrated_without_url_still_409(self):
        league = SimpleNamespace(migrated_at=datetime.now(timezone.utc), migrated_to_url=None)
        with Flask(__name__).app_context():
            resp, status = reject_if_migrated(league)
            body = resp.get_json()
        assert status == 409
        assert body == {"error": "league_migrated", "message": body["message"], "url": None}

    def test_to_dict_exposes_both_columns(self):
        from app.models.fantasy_league import FantasyLeague
        ts = datetime(2026, 12, 20, tzinfo=timezone.utc)
        lg = FantasyLeague(id=1, name="x", level_id=1, level_name="x", max_managers=4,
                           roster_skaters=5, draft_closes_at=ts,
                           migrated_at=ts, migrated_to_url=URL)
        d = lg.to_dict()
        assert d["migrated_at"] == ts.isoformat()
        assert d["migrated_to_url"] == URL


# ── job filters ──────────────────────────────────────────────────────────────

class _Result:
    def scalars(self):
        return self

    def all(self):
        return []

    def fetchall(self):
        return []

    def scalar_one(self):
        return 0


class _FakeSession:
    """Records every statement; returns no rows so each job ends after its select."""
    def __init__(self):
        self.statements = []

    def __call__(self):
        return self

    def execute(self, stmt, *a, **kw):
        self.statements.append(stmt)
        return _Result()

    def get(self, *a, **kw):
        return None

    def commit(self):
        pass

    def rollback(self):
        pass


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def _league_selects(session):
    return [s for s in map(_sql, session.statements) if "fantasy_leagues" in s]


@pytest.fixture
def fake_pred(monkeypatch):
    import app.db
    import app.services.fantasy_scoring_service as scoring
    import app.services.fantasy_trade_service as trade
    fake = _FakeSession()
    monkeypatch.setattr(app.db, "PredSession", fake)
    monkeypatch.setattr(scoring, "PredSession", fake)
    monkeypatch.setattr(trade, "PredSession", fake)
    return fake


@pytest.mark.parametrize("fn_name", [
    "score_active_leagues",
    "score_live_games",
    "auto_assign_seasons",
    "complete_finished_leagues",
])
def test_scoring_jobs_skip_migrated(fake_pred, fn_name):
    import app.services.fantasy_scoring_service as scoring
    getattr(scoring, fn_name)()
    selects = _league_selects(fake_pred)
    assert selects, f"{fn_name} issued no fantasy_leagues select"
    assert "fantasy_leagues.migrated_at IS NULL" in selects[0]


def test_trade_rounds_skip_migrated(fake_pred):
    from app.services.fantasy_trade_service import advance_active_trade_rounds
    assert advance_active_trade_rounds() == {"rounds": 0, "advanced": 0}
    sql = _sql(fake_pred.statements[0])
    assert "JOIN fantasy_leagues" in sql
    assert "fantasy_leagues.migrated_at IS NULL" in sql


class _FakeScheduler:
    def __init__(self, *a, **kw):
        self.jobs = {}
        self.running = False

    def add_job(self, func=None, id=None, **kw):
        self.jobs[id] = func

    def start(self):
        pass


@pytest.mark.parametrize("job_id", ["open_drafts", "advance_drafts"])
def test_draft_jobs_skip_migrated(fake_pred, monkeypatch, job_id):
    """open-draft (-> build_draft_queue) and advance-draft select leagues in grade_results."""
    from app.jobs import grade_results
    monkeypatch.setattr(grade_results, "BackgroundScheduler", _FakeScheduler)
    monkeypatch.setattr(grade_results, "_scheduler", None)
    monkeypatch.setattr("atexit.register", lambda *a, **kw: None)

    @contextmanager
    def _ctx():
        yield

    fake_app = SimpleNamespace(config={"TESTING": False}, app_context=_ctx)
    grade_results.start_scheduler(fake_app)
    jobs = grade_results._scheduler.jobs
    assert job_id in jobs, sorted(jobs)
    jobs[job_id]()
    selects = _league_selects(fake_pred)
    assert selects
    assert "fantasy_leagues.migrated_at IS NULL" in selects[0]

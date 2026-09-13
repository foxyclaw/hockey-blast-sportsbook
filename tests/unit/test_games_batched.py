"""
Unit tests for the batched /api/games serializer path — stub objects, no HB DB.

Covers:
  * build_game_maps issues ONE loader call per reference table for a page
  * a failing loader degrades the page (None names) and rolls back the HB session
  * _serialize_game(maps) full field set, incl. user_pick presence/absence
  * the user-pick map: one pred query, GLOBAL-league pick preferred, else oldest
  * _not_started_clause (SQL) agrees with lock_checker._game_start_dt (Python)
  * batched reference loaders (hb_ref_data) compose divisions + levels, cache skills
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Date, Integer, Time, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

from app.blueprints import games as games_mod
from app.blueprints.games import (
    _load_user_picks,
    _not_started_clause,
    _serialize_game,
    build_game_maps,
)
from app.services import hb_ref_data
from app.services.lock_checker import _game_start_dt
from app.services.ref_cache import TTLCache


# The shared conftest's autouse ``db_session`` fixture needs the Flask app + SQLite
# create_all (which currently fails on JSONB columns).  Override it here so these
# tests stay independent of that.
@pytest.fixture
def db_session():
    yield None


# ── Reference data ─────────────────────────────────────────────────────────────

TEAMS = {11: "Sharks", 12: "Kings", 13: "Ducks"}  # 14 is unknown on purpose
DIVISIONS = {
    5: {"id": 5, "name": "Adult Division 4B", "short_name": "4B"},
    6: {"id": 6, "name": "Adult Division O35", "short_name": "Adult Division O35"},
}
ORGS = {1: {"id": 1, "name": "Sharks Ice"}}
SKILLS = {11: 61.25, 12: 70.0, 13: 55.5}


def _game(gid, home, away, org_id=1, division_id=5, days_ahead=2):
    return SimpleNamespace(
        id=gid,
        date=date.today() + timedelta(days=days_ahead),
        time=time(19, 30),
        status="Scheduled",
        status_id=10,  # StatusId.SCHEDULED
        live_time=None,
        org_id=org_id,
        division_id=division_id,
        home_team_id=home,
        visitor_team_id=away,
    )


class _FakeHBSession:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def batched_loaders(monkeypatch):
    """Replace the batched loaders with recording fakes backed by the tables above."""
    calls = {"teams": [], "divisions": [], "orgs": [], "skills": []}

    def get_team_names(ids, hb_session):
        calls["teams"].append(list(ids))
        return {i: TEAMS.get(i) for i in ids if i is not None}

    def get_divisions(ids, hb_session):
        calls["divisions"].append(list(ids))
        return {i: DIVISIONS.get(i) for i in ids}

    def get_orgs(ids, hb_session):
        calls["orgs"].append(list(ids))
        return {i: ORGS.get(i) for i in ids}

    def get_team_avg_skills_cached(ids, hb_session):
        calls["skills"].append(list(ids))
        return {i: SKILLS.get(i) for i in ids}

    monkeypatch.setattr(games_mod, "get_team_names", get_team_names)
    monkeypatch.setattr(games_mod, "get_divisions", get_divisions)
    monkeypatch.setattr(games_mod, "get_orgs", get_orgs)
    monkeypatch.setattr(games_mod, "get_team_avg_skills_cached", get_team_avg_skills_cached)
    return calls


class TestBuildGameMaps:
    def test_one_loader_call_per_table_with_distinct_ids(self, batched_loaders):
        page = [
            _game(100, 11, 12),
            _game(101, 12, 13, division_id=6),
            _game(102, 13, 14, org_id=None, division_id=None),  # no org -> no skill lookup
        ]
        maps = build_game_maps(page, hb_session=_FakeHBSession())

        assert batched_loaders["teams"] == [[11, 12, 12, 13, 13, 14]]
        assert batched_loaders["divisions"] == [[5, 6]]
        assert batched_loaders["orgs"] == [[1, 1]]
        assert batched_loaders["skills"] == [[11, 12, 12, 13]]
        assert maps["teams"] == {11: "Sharks", 12: "Kings", 13: "Ducks", 14: None}
        assert maps["divisions"] == DIVISIONS
        assert maps["orgs"] == ORGS
        assert maps["skills"] == SKILLS
        assert maps["picks"] == {}  # anonymous request: always present, empty

    @pytest.mark.parametrize("loader", ["get_team_names", "get_team_avg_skills_cached"])
    def test_loader_failure_degrades_and_rolls_back(self, loader, batched_loaders, monkeypatch):
        def boom(ids, hb_session):
            raise RuntimeError("db down")

        monkeypatch.setattr(games_mod, loader, boom)
        hb = _FakeHBSession()
        game = _game(100, 11, 12)
        maps = build_game_maps([game], hb_session=hb)
        assert hb.rollbacks == 1  # aborted transaction cleared for later queries
        out = _serialize_game(game, maps)
        if loader == "get_team_names":
            assert out["home_team"]["name"] == "11"  # str(id) fallback
        else:
            assert out["home_team"]["avg_skill"] is None
            assert out["odds"]["has_skill_data"] is False


class TestSerializeGame:
    def test_full_field_set(self, batched_loaders):
        game = _game(100, 11, 12)
        out = _serialize_game(game, build_game_maps([game], _FakeHBSession()))
        assert out == {
            "game_id": 100,
            "scheduled_start": _game_start_dt(game).isoformat(),
            "lock_deadline": _game_start_dt(game).isoformat(),
            "status": "Scheduled",
            "is_pickable": True,
            "lock_reason": None,
            "is_live": False,
            "org_id": 1,
            "org": {"id": 1, "name": "Sharks Ice"},
            "division": {"id": 5, "name": "Adult Division 4B", "short_name": "4B"},
            "home_team": {"id": 11, "name": "Sharks", "avg_skill": 61.25},
            "away_team": {"id": 12, "name": "Kings", "avg_skill": 70.0},
            "odds": {
                "home_odds": 1.55,
                "visitor_odds": 2.2,
                "home_prob": 0.588,
                "visitor_prob": 0.412,
                "has_skill_data": True,
            },
        }
        assert "user_pick" not in out  # anonymous -> key absent, as before

    def test_missing_refs_and_started_game(self, batched_loaders):
        game = _game(105, 13, 14, org_id=None, division_id=99, days_ahead=-1)
        out = _serialize_game(game, build_game_maps([game], _FakeHBSession()))
        assert out["away_team"] == {"id": 14, "name": "14", "avg_skill": None}
        assert out["home_team"]["avg_skill"] is None  # no org -> no skill
        assert out["org"] is None and out["division"] is None
        assert out["is_pickable"] is False
        assert out["lock_reason"] == "Pick window has closed (game has started)"


# ── User picks ─────────────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return iter(self._rows)

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakePredSession:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self.rows)


def _pick_row(pid, game_id, league_id, join_code="ABC123"):
    pick = SimpleNamespace(
        id=pid,
        game_id=game_id,
        league_id=league_id,
        to_dict=lambda: {"id": pid, "game_id": game_id, "league_id": league_id},
    )
    return (pick, join_code)


class TestUserPicks:
    def test_single_query_global_league_preferred_else_oldest(self):
        user = SimpleNamespace(id=42)
        session = _FakePredSession(
            [
                _pick_row(1, 100, 1),  # oldest, private league
                _pick_row(2, 100, 2, join_code="GLOBAL01"),  # global -> wins
                _pick_row(3, 100, 3),
                _pick_row(4, 101, 1),  # only non-global picks -> oldest wins
                _pick_row(5, 101, 3),
            ]
        )
        picks = _load_user_picks([100, 101, 102], user, session)

        assert len(session.statements) == 1
        sql = str(session.statements[0])
        assert "JOIN pred_leagues" in sql
        assert "pred_picks.user_id = " in sql and "pred_picks.game_id IN " in sql
        assert picks[100].id == 2
        assert picks[101].id == 4
        assert 102 not in picks

    def test_no_game_ids_no_query(self):
        session = _FakePredSession([])
        assert _load_user_picks([], SimpleNamespace(id=1), session) == {}
        assert session.statements == []

    def test_serialize_uses_pick_map(self, batched_loaders):
        user = SimpleNamespace(id=42)
        page = [_game(100, 11, 12), _game(101, 12, 13)]
        session = _FakePredSession([_pick_row(7, 100, 1)])
        maps = build_game_maps(page, _FakeHBSession(), pred_user=user, pred_session=session)
        assert len(session.statements) == 1

        out = [_serialize_game(gm, maps, user) for gm in page]
        assert len(session.statements) == 1  # no per-game pick queries
        assert out[0]["user_pick"] == {"id": 7, "game_id": 100, "league_id": 1}
        assert out[1]["user_pick"] is None


# ── SQL "not started yet" filter vs. lock_checker's Python datetime ────────────


class _Base(DeclarativeBase):
    pass


class _G(_Base):
    __tablename__ = "g"
    id = Column(Integer, primary_key=True)
    date = Column(Date)
    time = Column(Time)


class TestNotStartedClause:
    def test_sql_clause_agrees_with_lock_checker_game_start_dt(self):
        now = datetime(2026, 9, 13, 18, 45, 10)
        today = now.date()
        rows = [
            (1, today - timedelta(days=1), time(23, 0)),  # yesterday -> drop
            (2, today, time(18, 0)),  # today, earlier -> drop
            (3, today, time(18, 45, 10)),  # today, exactly now -> keep (>=)
            (4, today, time(18, 45, 11)),  # today, later -> keep
            (5, today, None),  # today, no time = midnight -> drop
            (6, today + timedelta(days=1), None),  # tomorrow, no time -> keep
            (7, today + timedelta(days=1), time(0, 0)),  # tomorrow -> keep
            (8, today + timedelta(days=30), time(9, 0)),  # far future -> keep
        ]
        engine = create_engine("sqlite://")
        _Base.metadata.create_all(engine)
        with Session(engine) as s:
            s.add_all([_G(id=i, date=d, time=t) for i, d, t in rows])
            s.commit()
            sql_ids = set(
                s.execute(select(_G.id).where(_not_started_clause(_G, now))).scalars().all()
            )
            all_rows = s.execute(select(_G)).scalars().all()

        py_ids = {g.id for g in all_rows if _game_start_dt(g) >= now}
        assert sql_ids == py_ids == {3, 4, 6, 7, 8}


# ── hb_ref_data batched loaders (fake session, real composition + cache) ────────


class _FakeQuerySession:
    """Answers select() statements from in-memory tables keyed by table name."""

    def __init__(self, tables):
        self.tables = tables
        self.queries = []

    def execute(self, stmt):
        table = stmt.get_final_froms()[0].name
        self.queries.append(table)
        return _FakeResult(self.tables[table])


@pytest.fixture
def fresh_caches(monkeypatch):
    for name in ("team_cache", "division_cache", "level_cache", "org_cache", "skill_cache"):
        monkeypatch.setattr(hb_ref_data, name, TTLCache(ttl_seconds=600, enabled=True))


class TestHBRefData:
    def test_divisions_compose_levels_in_two_queries(self, fresh_caches):
        session = _FakeQuerySession(
            {
                "divisions": [
                    SimpleNamespace(id=5, level="Adult Division 4B", level_id=50),
                    SimpleNamespace(id=6, level="Adult Division O35", level_id=60),
                    SimpleNamespace(id=7, level="Adult Division 7", level_id=None),
                ],
                "levels": [
                    SimpleNamespace(id=50, short_name="4B", level_name="Adult Division 4B"),
                    SimpleNamespace(id=60, short_name=None, level_name="O35 long"),
                ],
            }
        )
        out = hb_ref_data.get_divisions([5, 6, 7, 8, 5], session)
        assert session.queries == ["divisions", "levels"]
        assert out == {
            5: {"id": 5, "name": "Adult Division 4B", "short_name": "4B"},
            6: {"id": 6, "name": "Adult Division O35", "short_name": "O35 long"},
            7: {"id": 7, "name": "Adult Division 7", "short_name": "Adult Division 7"},
            8: None,
        }
        # warm cache: no further queries, same answer
        assert hb_ref_data.get_divisions([5, 6, 7, 8], session) == out
        assert session.queries == ["divisions", "levels"]

    def test_teams_and_orgs(self, fresh_caches):
        session = _FakeQuerySession(
            {
                "teams": [SimpleNamespace(id=11, name="Sharks")],
                "organizations": [SimpleNamespace(id=1, organization_name="Sharks Ice")],
            }
        )
        assert hb_ref_data.get_team_names([11, 12], session) == {11: "Sharks", 12: None}
        assert hb_ref_data.get_orgs([1, 2], session) == {
            1: {"id": 1, "name": "Sharks Ice"},
            2: None,
        }
        assert session.queries == ["teams", "organizations"]
        hb_ref_data.get_team_names([11, 12], session)
        assert session.queries == ["teams", "organizations"]  # cache hit (incl. negative)

    def test_skills_cached_per_team(self, fresh_caches, monkeypatch):
        from app.services import skill_snapshot

        calls = []

        def fake_batch(ids, hb_session=None):
            calls.append(list(ids))
            return {i: SKILLS[i] for i in ids if i in SKILLS}

        monkeypatch.setattr(skill_snapshot, "get_team_avg_skills", fake_batch)
        out = hb_ref_data.get_team_avg_skills_cached([11, 14, 11], hb_session=None)
        assert out == {11: 61.25, 14: None}
        # 11 and 14 (negative) now cached; only 12 is fetched
        out = hb_ref_data.get_team_avg_skills_cached([11, 12, 14], hb_session=None)
        assert out == {11: 61.25, 12: 70.0, 14: None}
        assert calls == [[11, 14], [12]]

    def test_disabled_cache_queries_every_time(self, monkeypatch):
        monkeypatch.setattr(hb_ref_data, "team_cache", TTLCache(enabled=False))
        session = _FakeQuerySession({"teams": [SimpleNamespace(id=11, name="Sharks")]})
        hb_ref_data.get_team_names([11], session)
        hb_ref_data.get_team_names([11], session)
        assert session.queries == ["teams", "teams"]


# ── Compile-only smoke tests for the real batched statements ───────────────────


class TestCompiledStatements:
    def test_team_avg_skills_is_one_windowed_query(self):
        pytest.importorskip("hockey_blast_common_lib.models")
        from hockey_blast_common_lib.models import GameRoster, Human
        from sqlalchemy.dialects import postgresql

        from app.services.skill_snapshot import build_team_avg_skills_stmt

        sql = str(
            build_team_avg_skills_stmt(GameRoster, Human, [11, 12]).compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert (
            "row_number() OVER (PARTITION BY game_rosters.team_id ORDER BY game_rosters.id DESC)"
            in sql
        )
        assert "game_rosters.team_id IN (11, 12)" in sql
        assert "game_rosters.role != 'G'" in sql
        assert "recent.rn <= 200" in sql
        assert "SELECT DISTINCT" in sql
        assert "humans.skater_skill_value > 0" in sql
        assert "GROUP BY recent_humans.team_id" in sql

    def test_my_picks_count_keeps_joins(self):
        from sqlalchemy import func

        from app.models.pred_pick import PredPick
        from app.models.pred_result import PredResult

        stmt = (
            select(PredPick)
            .where(PredPick.user_id == 1)
            .join(PredResult, PredPick.id == PredResult.pick_id)
            .order_by(PredPick.game_scheduled_start.desc())
        )
        sql = str(stmt.order_by(None).with_only_columns(func.count(PredPick.id)))
        assert sql.startswith("SELECT count(pred_picks.id)")
        assert "JOIN pred_results" in sql
        assert "ORDER BY" not in sql

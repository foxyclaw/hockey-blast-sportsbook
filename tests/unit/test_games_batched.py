"""
Unit tests for the batched /api/games serializer path — stub objects, no HB DB.

Covers:
  * build_game_maps issues ONE loader call per reference table for a page
  * _serialize_game(maps=...) produces exactly the same dict as the per-id fallback
  * the user-pick map: one pred query, first pick per game, None when absent
  * _not_started_clause matches the old Python filter row-for-row (SQLite)
  * batched reference loaders (hb_ref_data) compose divisions + levels and hit cache
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Date, Integer, Time, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

from app.blueprints import games as games_mod
from app.blueprints.games import (
    _game_start_dt,
    _load_user_picks,
    _not_started_clause,
    _serialize_game,
    build_game_maps,
)
from app.services import hb_ref_data
from app.services.ref_cache import TTLCache


# The shared conftest's autouse ``db_session`` fixture needs the Flask app + SQLite
# create_all (which currently fails on JSONB columns).  Override it here so these
# tests stay independent of that.
@pytest.fixture
def db_session():
    yield None


# ── Reference data used by both the batched and fallback paths ──────────────────

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

    def get_team_avg_skills(ids):
        calls["skills"].append(list(ids))
        return {i: SKILLS[i] for i in ids if i in SKILLS}

    monkeypatch.setattr(games_mod, "get_team_names", get_team_names)
    monkeypatch.setattr(games_mod, "get_divisions", get_divisions)
    monkeypatch.setattr(games_mod, "get_orgs", get_orgs)
    monkeypatch.setattr(games_mod, "get_team_avg_skills", get_team_avg_skills)
    return calls


@pytest.fixture
def fallback_lookups(monkeypatch):
    """Replace the old per-id helpers with fakes backed by the same tables."""
    calls = {"team": 0, "division": 0, "org": 0, "skill": 0}

    def _get_team(team_id, hb_session):
        calls["team"] += 1
        return SimpleNamespace(name=TEAMS[team_id]) if team_id in TEAMS else None

    def _get_division(division_id, hb_session):
        calls["division"] += 1
        return dict(DIVISIONS[division_id]) if division_id in DIVISIONS else None

    def _get_org(org_id, hb_session):
        calls["org"] += 1
        return dict(ORGS[org_id]) if org_id in ORGS else None

    def get_team_avg_skill(team_id, org_id=None):
        calls["skill"] += 1
        return SKILLS.get(team_id)

    monkeypatch.setattr(games_mod, "_get_team", _get_team)
    monkeypatch.setattr(games_mod, "_get_division", _get_division)
    monkeypatch.setattr(games_mod, "_get_org", _get_org)
    monkeypatch.setattr(games_mod, "get_team_avg_skill", get_team_avg_skill)
    return calls


class TestBuildGameMaps:
    def test_one_loader_call_per_table_with_distinct_ids(self, batched_loaders):
        page = [
            _game(100, 11, 12),
            _game(101, 12, 13, division_id=6),
            _game(102, 13, 14, org_id=None, division_id=None),  # no org -> no skill lookup
        ]
        maps = build_game_maps(page, hb_session=None)

        assert batched_loaders["teams"] == [[11, 12, 12, 13, 13, 14]]
        assert batched_loaders["divisions"] == [[5, 6]]
        assert batched_loaders["orgs"] == [[1, 1]]
        assert batched_loaders["skills"] == [[11, 12, 12, 13]]
        assert maps["teams"] == {11: "Sharks", 12: "Kings", 13: "Ducks", 14: None}
        assert maps["divisions"] == DIVISIONS
        assert maps["orgs"] == ORGS
        assert maps["skills"] == SKILLS
        assert "picks" not in maps  # anonymous request

    def test_loader_failure_degrades_like_old_helpers(self, batched_loaders, monkeypatch):
        def boom(ids, hb_session):
            raise RuntimeError("db down")

        monkeypatch.setattr(games_mod, "get_team_names", boom)
        maps = build_game_maps([_game(100, 11, 12)], hb_session=None)
        assert maps["teams"] == {}
        out = _serialize_game(_game(100, 11, 12), None, maps=maps)
        assert out["home_team"]["name"] == "11"  # str(id) fallback, as before


class TestSerializeGameEquivalence:
    @pytest.mark.parametrize(
        "game",
        [
            _game(100, 11, 12),
            _game(101, 12, 13, division_id=6),
            _game(102, 13, 14),  # unknown away team -> name falls back to str(id)
            _game(103, 11, 12, org_id=None),  # no org -> org None, skills None
            _game(104, 11, 12, division_id=None),
            _game(105, 11, 12, division_id=99),  # unknown division -> None
            _game(106, 11, 12, days_ahead=-1),  # already started -> not pickable
        ],
    )
    def test_maps_path_matches_fallback_path(self, game, batched_loaders, fallback_lookups):
        maps = build_game_maps([game], hb_session=None)
        batched = _serialize_game(game, None, maps=maps)
        fallback = _serialize_game(game, None)  # maps=None -> old per-id lookups
        assert batched == fallback
        assert list(batched.keys()) == list(fallback.keys())

    def test_full_field_set(self, batched_loaders):
        game = _game(100, 11, 12)
        out = _serialize_game(game, None, maps=build_game_maps([game], None))
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
        assert "user_pick" not in out


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
    def __init__(self, picks):
        self.picks = picks
        self.statements = []

    def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self.picks)


def _pick(pid, game_id, league_id):
    return SimpleNamespace(
        id=pid,
        game_id=game_id,
        league_id=league_id,
        to_dict=lambda: {"id": pid, "game_id": game_id, "league_id": league_id},
    )


class TestUserPicks:
    def test_single_query_first_pick_per_game(self):
        user = SimpleNamespace(id=42)
        session = _FakePredSession([_pick(1, 100, 1), _pick(2, 100, 2), _pick(3, 101, 1)])
        picks = _load_user_picks([100, 101, 102], user, session)

        assert len(session.statements) == 1
        sql = str(session.statements[0])
        assert "pred_picks.user_id = " in sql and "pred_picks.game_id IN " in sql
        assert picks[100].id == 1  # first (lowest id) wins when a user has several
        assert picks[101].id == 3
        assert 102 not in picks

    def test_no_game_ids_no_query(self):
        session = _FakePredSession([])
        assert _load_user_picks([], SimpleNamespace(id=1), session) == {}
        assert session.statements == []

    def test_serialize_uses_pick_map(self, batched_loaders):
        user = SimpleNamespace(id=42)
        page = [_game(100, 11, 12), _game(101, 12, 13)]
        session = _FakePredSession([_pick(7, 100, 1)])
        maps = build_game_maps(page, None, pred_user=user, pred_session=session)
        assert len(session.statements) == 1

        out = [_serialize_game(gm, None, user, session, maps=maps) for gm in page]
        assert len(session.statements) == 1  # no per-game pick queries
        assert out[0]["user_pick"] == {"id": 7, "game_id": 100, "league_id": 1}
        assert out[1]["user_pick"] is None

    def test_fallback_path_still_queries_per_game(self, fallback_lookups):
        user = SimpleNamespace(id=42)
        session = _FakePredSession([_pick(7, 100, 1)])
        out = _serialize_game(_game(100, 11, 12), None, user, session)
        assert len(session.statements) == 1
        assert out["user_pick"]["id"] == 7


# ── SQL "not started yet" filter vs. the old Python filter ─────────────────────


class _Base(DeclarativeBase):
    pass


class _G(_Base):
    __tablename__ = "g"
    id = Column(Integer, primary_key=True)
    date = Column(Date)
    time = Column(Time)


class TestNotStartedClause:
    def test_matches_python_filter_row_for_row(self):
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

        py_ids = {g.id for g in all_rows if _game_start_dt(g) is None or _game_start_dt(g) >= now}
        assert sql_ids == py_ids == {3, 4, 6, 7, 8}


# ── hb_ref_data batched loaders (fake session, real composition + cache) ────────


class _FakeHBSession:
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
    for name in ("team_cache", "division_cache", "level_cache", "org_cache"):
        monkeypatch.setattr(hb_ref_data, name, TTLCache(ttl_seconds=600, enabled=True))


class TestHBRefData:
    def test_divisions_compose_levels_in_two_queries(self, fresh_caches):
        session = _FakeHBSession(
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
        session = _FakeHBSession(
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

    def test_disabled_cache_queries_every_time(self, monkeypatch):
        monkeypatch.setattr(hb_ref_data, "team_cache", TTLCache(enabled=False))
        session = _FakeHBSession({"teams": [SimpleNamespace(id=11, name="Sharks")]})
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

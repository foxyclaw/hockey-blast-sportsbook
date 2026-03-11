# Hockey Blast Predictions — Technical Design Document

**Version:** 0.1.0  
**Date:** 2026-03-11  
**Author:** FoxyClaw (AI Architect)  
**Status:** Draft — awaiting Pasha review

---

## Table of Contents

1. [Overview & Product Vision](#1-overview--product-vision)
2. [Architecture](#2-architecture)
3. [Database Schema](#3-database-schema)
4. [Scoring System](#4-scoring-system)
5. [API Design](#5-api-design)
6. [Pick-Em UX Flow](#6-pick-em-ux-flow)
7. [Implementation Phases](#7-implementation-phases)
8. [Repo Structure](#8-repo-structure)
9. [Key Dependencies](#9-key-dependencies)
10. [Open Questions for Pasha](#10-open-questions-for-pasha)

---

## 1. Overview & Product Vision

### What Is This?

Hockey Blast Predictions is a pick-em game layered on top of the existing [hockey-blast.com](https://hockey-blast.com) platform. Players predict the outcome of real scheduled recreational hockey games before puck drop, earn points based on accuracy and boldness, and compete on private league leaderboards.

This is **not gambling**. There is no platform-handled money. Points are imaginary internet points. If friends want to put $5 on the line among themselves, that's entirely their business — the app doesn't know or care.

### Core Experience

> *"I think the Sharks Ice Monday Div 3 Puck Bunnies are going to upset the Mighty Quacks tonight. I'm putting 3x confidence on it."*

The player selects the winner of an upcoming game, optionally assigns a confidence multiplier, and locks their pick before the game starts. After the game resolves, points are awarded automatically. Leagues track cumulative standings across a season.

### Why It's Interesting

- **Upsets are rewarded.** Picking the underdog (lower `skater_skill_value` average) yields a bonus. This prevents everyone from always picking the top seed.
- **Confidence multipliers add risk/reward.** Players can commit hard to a pick and earn big — or lose big.
- **Leagues keep it social.** Pick-em without a leaderboard is just a spreadsheet. Leagues are the product.
- **8,000+ scheduled games** means there's always something to pick on. Multiple orgs, skill levels, and divisions keep it fresh.

### Non-Goals (v1)

- No real-money wagering, no platform-managed pools
- No fantasy roster building (that's a separate product)
- No live in-game picks (picks lock at puck drop)
- No mobile app (mobile-responsive web only)

---

## 2. Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser / App                         │
│                   (React or Jinja2 + HTMX)                  │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTPS
┌────────────────────────────▼────────────────────────────────┐
│              hockey-blast-predictions (Flask)                │
│                                                              │
│   blueprints/                                                │
│     auth.py        ← Auth0 OIDC callback + JWT validation   │
│     picks.py       ← Submit / view picks                    │
│     leagues.py     ← Create / join / manage leagues         │
│     results.py     ← Scoring engine + standings             │
│     games.py       ← Game browser (read-only from HB DB)    │
│                                                              │
│   services/                                                  │
│     scoring.py     ← Core scoring logic                     │
│     lock_checker.py← Pick lock validation                   │
│     result_grader.py← Post-game grading job                 │
└────────────┬───────────────────────────────┬────────────────┘
             │                               │
┌────────────▼───────────┐   ┌──────────────▼───────────────┐
│  predictions_db         │   │   hockey_blast DB             │
│  (PostgreSQL)           │   │   (PostgreSQL, read-only)     │
│                         │   │                               │
│  pred_users             │   │   games                       │
│  pred_leagues           │   │   teams                       │
│  pred_league_members    │   │   humans                      │
│  pred_picks             │   │   org_stats_skater            │
│  pred_results           │   │   divisions, seasons, etc.    │
│  pred_league_standings  │   │                               │
└─────────────────────────┘   └───────────────────────────────┘
             │
┌────────────▼───────────┐
│  Auth0                  │
│  (OIDC / JWT)           │
└─────────────────────────┘
```

### Two-Database Strategy

The predictions app uses **two separate databases**:

| Database | Purpose | Access |
|---|---|---|
| `hockey_blast` | Source of truth for games, teams, players, stats | **Read-only** via `hockey_blast_common_lib` models |
| `predictions_db` | All predictions-specific data | Read + Write |

This is non-negotiable. We never write to `hockey_blast`. We import `hockey_blast_common_lib` as a pip dependency and bind its models to the HB connection at app startup.

### SQLAlchemy Dual-Bind Pattern

```python
# app/db.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# Read-only connection to hockey_blast
hb_engine = create_engine(config.HB_DATABASE_URL, pool_pre_ping=True)
HBSession = scoped_session(sessionmaker(bind=hb_engine))

# Read/write predictions DB
pred_engine = create_engine(config.PRED_DATABASE_URL, pool_pre_ping=True)
PredSession = scoped_session(sessionmaker(bind=pred_engine))
```

All prediction models use `PredSession`. All hockey_blast_common_lib models use `HBSession`. Never mix them.

### Background Jobs

A lightweight APScheduler (or Celery if needed) runs two periodic jobs:

1. **`grade_completed_games`** — runs every 15 minutes. Finds `PredPick` records where the referenced game has a final status (`Final`, `Final/OT`, `Final/SO`, `Forfeit`) and no corresponding `PredResult` yet. Grades them, writes `PredResult`, updates `PredLeagueStandings`.

2. **`lock_expired_picks`** — not strictly needed (lock is enforced at pick submission time), but useful as a safety net.

### Auth Flow

```
User clicks "Sign In"
  → Redirect to Auth0 (Google / Facebook / Apple)
  → Auth0 returns JWT to /auth/callback
  → Flask validates JWT, extracts sub (auth0|xxx or google-oauth2|xxx)
  → Upsert PredUser(auth0_sub=...) on first login
  → Store JWT in HttpOnly cookie (or session)
  → All subsequent API calls validated via @require_auth decorator
```

---

## 3. Database Schema

### Design Principles

- All foreign keys to hockey_blast data use integer IDs (e.g., `game_id`, `team_id`) — **not** SQLAlchemy ForeignKey constraints (since they live in a different DB). Store as plain `Integer` columns.
- All prediction-native relationships use proper FK constraints within `predictions_db`.
- Timestamps always `timezone=True` (UTC stored, displayed in user's local TZ on the frontend).
- Soft deletes where appropriate (`is_active` flag on leagues).

---

### `PredUser`

Represents a registered user of the predictions platform.

```python
# app/models/pred_user.py

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.db import PredBase  # declarative_base() bound to pred_engine

class PredUser(PredBase):
    """
    A user of the predictions platform, authenticated via Auth0.
    One PredUser per Auth0 subject (sub claim).
    """
    __tablename__ = "pred_users"

    id = Column(Integer, primary_key=True)
    auth0_sub = Column(String(128), unique=True, nullable=False, index=True)
    # Sub format: "google-oauth2|1234567890" or "auth0|abc123"

    display_name = Column(String(64), nullable=False)
    # Sourced from Auth0 name claim on first login; user can update.

    email = Column(String(256), nullable=True)
    # May be null if user denies email scope (Apple Sign In).

    avatar_url = Column(String(512), nullable=True)
    # Sourced from Auth0 picture claim; optional.

    # Linked hockey_blast human (optional — user can connect their HB profile)
    hb_human_id = Column(Integer, nullable=True, index=True)
    # References hockey_blast.humans.id — no FK constraint (cross-DB)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    league_memberships = relationship("PredLeagueMember", back_populates="user", lazy="dynamic")
    picks = relationship("PredPick", back_populates="user", lazy="dynamic")

    def __repr__(self):
        return f"<PredUser {self.id} {self.display_name!r}>"
```

---

### `PredLeague`

A private pick-em league. Users create leagues and invite others via a join code.

```python
# app/models/pred_league.py

import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text
from sqlalchemy.orm import relationship
from app.db import PredBase

import enum

class LeagueScope(enum.Enum):
    """Which games this league covers."""
    ALL_ORGS = "all_orgs"
    ORG = "org"          # Single org (org_id set)
    DIVISION = "division" # Single division (division_id set)
    CUSTOM = "custom"    # Admin manually picks game pools (stretch goal)


class PredLeague(PredBase):
    """
    A pick-em league. Has members, a game scope, and a season window.
    """
    __tablename__ = "pred_leagues"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)

    join_code = Column(
        String(16),
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(8).upper()[:8]
    )
    # 8-char alphanumeric code for joining. e.g. "X7KP2MNA"

    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    # Public leagues appear in browse listing (stretch goal)

    # Game scope — which games count for picks in this league
    scope = Column(Enum(LeagueScope), default=LeagueScope.ALL_ORGS, nullable=False)
    org_id = Column(Integer, nullable=True)        # References hockey_blast.organizations.id
    division_id = Column(Integer, nullable=True)   # References hockey_blast.divisions.id
    season_id = Column(Integer, nullable=True)     # References hockey_blast.seasons.id
    # If season_id is set, only games within that season are pickable.
    # If null, all upcoming scheduled games matching scope are pickable.

    # Commissioner (league owner)
    commissioner_id = Column(Integer, nullable=False)
    # References pred_users.id — proper FK within predictions_db
    # (Not using FK constraint here to keep model simple; enforce in service layer)

    max_members = Column(Integer, default=50, nullable=False)

    # Scoring config overrides (use defaults if null)
    correct_pick_base_points = Column(Integer, default=10, nullable=False)
    upset_bonus_enabled = Column(Boolean, default=True, nullable=False)
    confidence_multiplier_enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    members = relationship("PredLeagueMember", back_populates="league", lazy="dynamic")
    standings = relationship("PredLeagueStandings", back_populates="league", lazy="dynamic")

    def __repr__(self):
        return f"<PredLeague {self.id} {self.name!r} [{self.join_code}]>"
```

---

### `PredLeagueMember`

Junction table: user ↔ league membership with role.

```python
# app/models/pred_league_member.py

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Boolean, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db import PredBase
import enum

class MemberRole(enum.Enum):
    COMMISSIONER = "commissioner"
    MEMBER = "member"


class PredLeagueMember(PredBase):
    """
    Membership record for a user in a league.
    Enforces unique (user_id, league_id) at DB level.
    """
    __tablename__ = "pred_league_members"
    __table_args__ = (
        UniqueConstraint("user_id", "league_id", name="uq_user_league"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("pred_users.id"), nullable=False, index=True)
    league_id = Column(Integer, ForeignKey("pred_leagues.id"), nullable=False, index=True)
    role = Column(Enum(MemberRole), default=MemberRole.MEMBER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # Soft-delete: set is_active=False when user leaves league

    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("PredUser", back_populates="league_memberships")
    league = relationship("PredLeague", back_populates="members")

    def __repr__(self):
        return f"<PredLeagueMember user={self.user_id} league={self.league_id} role={self.role}>"
```

---

### `PredPick`

A single pick: user predicts game winner, optionally with a confidence multiplier.

```python
# app/models/pred_pick.py

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, Boolean, DateTime, Enum,
    ForeignKey, UniqueConstraint, CheckConstraint, Numeric
)
from sqlalchemy.orm import relationship
from app.db import PredBase
import enum

class PickConfidence(enum.Enum):
    LOW = 1     # 1x multiplier
    MED = 2     # 2x multiplier
    HIGH = 3    # 3x multiplier


class PredPick(PredBase):
    """
    One user's prediction for one game within one league.

    Locking: picks are locked when game.scheduled_start <= now().
    Lock is enforced at the service layer (lock_checker.py), not here.

    Cross-DB references (no FK constraints):
      - game_id       → hockey_blast.games.id
      - picked_team_id → hockey_blast.teams.id
      - home_team_id   → hockey_blast.teams.id
      - away_team_id   → hockey_blast.teams.id
    """
    __tablename__ = "pred_picks"
    __table_args__ = (
        # One pick per user per game per league
        UniqueConstraint("user_id", "game_id", "league_id", name="uq_pick_user_game_league"),
        # Confidence must be 1, 2, or 3
        CheckConstraint("confidence IN (1, 2, 3)", name="ck_confidence_valid"),
    )

    id = Column(Integer, primary_key=True)

    # Who picked
    user_id = Column(Integer, ForeignKey("pred_users.id"), nullable=False, index=True)
    league_id = Column(Integer, ForeignKey("pred_leagues.id"), nullable=False, index=True)

    # What game
    game_id = Column(Integer, nullable=False, index=True)
    # Denormalized for query convenience — avoids HB DB join on every standings query
    game_scheduled_start = Column(DateTime(timezone=True), nullable=False)
    home_team_id = Column(Integer, nullable=False)
    away_team_id = Column(Integer, nullable=False)

    # The pick itself
    picked_team_id = Column(Integer, nullable=False)
    # Must be home_team_id or away_team_id — enforced in service layer

    confidence = Column(Integer, default=1, nullable=False)
    # 1 = low (1x), 2 = med (2x), 3 = high (3x)

    # Upset detection snapshot — captured at pick submission time
    # Snapshot because skill values can change; we want point-in-time fairness
    home_team_avg_skill = Column(Numeric(6, 2), nullable=True)
    away_team_avg_skill = Column(Numeric(6, 2), nullable=True)
    # skill_value: 0 = best, 100 = worst
    # "Upset" = picking the team with HIGHER avg skill value (the weaker team)

    picked_team_avg_skill = Column(Numeric(6, 2), nullable=True)
    opponent_avg_skill = Column(Numeric(6, 2), nullable=True)
    skill_differential = Column(Numeric(6, 2), nullable=True)
    # = opponent_avg_skill - picked_team_avg_skill
    # Positive → picked the underdog (upset pick)
    # Negative → picked the favorite

    is_upset_pick = Column(Boolean, default=False, nullable=False)
    # True if picked_team_avg_skill > opponent_avg_skill (picked the weaker team)

    is_locked = Column(Boolean, default=False, nullable=False)
    # Set True by service layer once game_scheduled_start passes

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("PredUser", back_populates="picks")
    result = relationship("PredResult", back_populates="pick", uselist=False)

    def __repr__(self):
        return (
            f"<PredPick user={self.user_id} game={self.game_id} "
            f"team={self.picked_team_id} conf={self.confidence}>"
        )
```

---

### `PredResult`

The graded outcome of a pick. Created by the background grader job after a game resolves.

```python
# app/models/pred_result.py

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, Boolean, DateTime, Numeric,
    ForeignKey, String
)
from sqlalchemy.orm import relationship
from app.db import PredBase


class PredResult(PredBase):
    """
    Graded result for a single PredPick.
    Created once per pick after game reaches a final status.

    Points formula:
        if correct:
            base = league.correct_pick_base_points (default 10)
            upset_bonus = max(0, floor(skill_differential * 0.5))  [if enabled]
            total = (base + upset_bonus) * confidence
        else:
            total = 0
    """
    __tablename__ = "pred_results"

    id = Column(Integer, primary_key=True)
    pick_id = Column(Integer, ForeignKey("pred_picks.id"), unique=True, nullable=False, index=True)

    # Actual game outcome (cross-DB ref, no FK)
    actual_winner_team_id = Column(Integer, nullable=True)
    # Null for forfeits/ties; we handle those as "no result" (0 points, pick not counted)

    game_final_status = Column(String(32), nullable=False)
    # "Final", "Final/OT", "Final/SO", "Forfeit", "CANCELED"

    is_correct = Column(Boolean, nullable=False, default=False)
    # True if picked_team_id == actual_winner_team_id

    # Points breakdown
    base_points = Column(Integer, default=0, nullable=False)
    upset_bonus_points = Column(Integer, default=0, nullable=False)
    pre_multiplier_points = Column(Integer, default=0, nullable=False)
    # = base_points + upset_bonus_points
    confidence_multiplier = Column(Integer, default=1, nullable=False)
    # Copied from pick.confidence
    total_points = Column(Integer, default=0, nullable=False)
    # = pre_multiplier_points * confidence_multiplier

    graded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    pick = relationship("PredPick", back_populates="result")

    def __repr__(self):
        return (
            f"<PredResult pick={self.pick_id} correct={self.is_correct} "
            f"pts={self.total_points}>"
        )
```

---

### `PredLeagueStandings`

Materialized per-user standings within a league. Rebuilt/updated by the grader job.

```python
# app/models/pred_league_standings.py

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, Boolean, DateTime, Numeric,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db import PredBase


class PredLeagueStandings(PredBase):
    """
    Rolling standings for a user within a league.
    Updated incrementally each time a PredResult is created for that user+league.

    This is a materialized summary — always derived from PredResult rows.
    Never update this directly; always update via standings_service.recalculate().
    """
    __tablename__ = "pred_league_standings"
    __table_args__ = (
        UniqueConstraint("user_id", "league_id", name="uq_standings_user_league"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("pred_users.id"), nullable=False, index=True)
    league_id = Column(Integer, ForeignKey("pred_leagues.id"), nullable=False, index=True)

    # Cumulative stats
    total_points = Column(Integer, default=0, nullable=False)
    total_picks = Column(Integer, default=0, nullable=False)
    correct_picks = Column(Integer, default=0, nullable=False)
    upset_picks_correct = Column(Integer, default=0, nullable=False)
    # Counts of high-confidence correct picks
    high_conf_correct = Column(Integer, default=0, nullable=False)

    pick_accuracy = Column(Numeric(5, 2), default=0.0, nullable=False)
    # correct_picks / total_picks * 100 (percentage)

    # Ranking (recomputed after each grading batch)
    rank = Column(Integer, nullable=True)
    # 1 = top of leaderboard; null until first game graded

    last_updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("PredUser")
    league = relationship("PredLeague", back_populates="standings")

    def __repr__(self):
        return (
            f"<PredLeagueStandings user={self.user_id} league={self.league_id} "
            f"pts={self.total_points} rank={self.rank}>"
        )
```

---

### Pick Lock Logic

Locking is **time-based** and enforced in the service layer, never in the model.

```python
# app/services/lock_checker.py

from datetime import datetime, timezone
from app.db import HBSession
from hockey_blast_common_lib.models import Game


def is_game_pickable(game_id: int) -> tuple[bool, str]:
    """
    Returns (True, "") if a pick can be submitted/modified for this game.
    Returns (False, reason) if the game is locked.

    Lock conditions:
    1. Game does not exist or status is not "Scheduled"
    2. game.game_date_time <= now() (game has started or passed)
    3. game.live_time is not null (game is live)
    """
    session = HBSession()
    game = session.query(Game).filter(Game.id == game_id).first()

    if not game:
        return False, "Game not found"

    if game.status != "Scheduled":
        return False, f"Game is already {game.status}"

    if game.live_time is not None:
        return False, "Game is live"

    now = datetime.now(timezone.utc)
    # game.game_date_time should be timezone-aware; handle naive timestamps defensively
    scheduled = game.game_date_time
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)

    if now >= scheduled:
        return False, "Pick window has closed (game has started)"

    return True, ""


def get_lock_deadline(game_id: int) -> datetime | None:
    """Returns the datetime when picks lock for this game (= game start time)."""
    session = HBSession()
    game = session.query(Game).filter(Game.id == game_id).first()
    if not game:
        return None
    scheduled = game.game_date_time
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    return scheduled
```

---

### Skill Snapshot Logic

When a pick is submitted, we immediately snapshot team skill averages from `org_stats_skater`.

```python
# app/services/skill_snapshot.py

from sqlalchemy import func
from app.db import HBSession
from hockey_blast_common_lib.models import GameRoster, OrgStatsSkater


def get_team_avg_skill(team_id: int, org_id: int) -> float | None:
    """
    Returns the average skater_skill_value for a team's rostered skaters
    using the pre-aggregated org_stats_skater table.

    Returns None if no stats found (new team, no history).
    """
    session = HBSession()
    result = (
        session.query(func.avg(OrgStatsSkater.skater_skill_value))
        .filter(
            OrgStatsSkater.team_id == team_id,
            OrgStatsSkater.org_id == org_id,
        )
        .scalar()
    )
    return float(result) if result is not None else None
```

---

## 4. Scoring System

### Core Formula

```
if pick is correct:
    base_points         = league.correct_pick_base_points  (default: 10)
    upset_bonus         = max(0, floor(skill_differential × UPSET_SCALE))
    pre_multiplier      = base_points + upset_bonus
    total_points        = pre_multiplier × confidence_multiplier
else:
    total_points        = 0

UPSET_SCALE = 0.5   (tunable per league in future)
skill_differential = opponent_avg_skill − picked_team_avg_skill
```

**Recall:** `skater_skill_value`: 0 = elite, 100 = worst. So if you pick the team with *higher* skill value (the worse team), the differential is positive → bonus.

### Scoring Table

| Scenario | Skill Diff | Conf | Base | Upset Bonus | Pre-mult | Multiplier | **Total** |
|---|---|---|---|---|---|---|---|
| Correct, even matchup, low conf | 0 | 1x | 10 | 0 | 10 | 1 | **10** |
| Correct, even matchup, med conf | 0 | 2x | 10 | 0 | 10 | 2 | **20** |
| Correct, even matchup, high conf | 0 | 3x | 10 | 0 | 10 | 3 | **30** |
| Correct, mild upset (+10 diff), low conf | +10 | 1x | 10 | 5 | 15 | 1 | **15** |
| Correct, mild upset (+10 diff), high conf | +10 | 3x | 10 | 5 | 15 | 3 | **45** |
| Correct, big upset (+30 diff), low conf | +30 | 1x | 10 | 15 | 25 | 1 | **25** |
| Correct, big upset (+30 diff), high conf | +30 | 3x | 10 | 15 | 25 | 3 | **75** |
| Correct, extreme upset (+50 diff), high conf | +50 | 3x | 10 | 25 | 35 | 3 | **105** |
| Wrong pick (any) | any | any | — | — | — | — | **0** |
| Forfeit / CANCELED game | — | — | — | — | — | — | **0, pick voided** |

### Edge Cases

| Situation | Handling |
|---|---|
| `Forfeit` game | Pick voided — 0 points, not counted in accuracy stats |
| `CANCELED` game | Pick voided — 0 points, not counted in accuracy stats |
| `Final/OT` or `Final/SO` | Winner is the team with more goals — normal scoring applies |
| No skill data available for one/both teams | `upset_bonus = 0`, `is_upset_pick = False` |
| Tie game (shouldn't exist in hockey) | Treated as no winner, pick voided |
| User picks tie (not offered in UI) | N/A — UI only offers home/away team |

### Example Walkthrough

> **Game:** Puck Bunnies (avg skill: 55) vs. Mighty Quacks (avg skill: 30)
>
> Pasha picks **Puck Bunnies** (the weaker team) with **3x confidence**.
>
> - `skill_differential` = 30 − 55 = −25 → wait, that's negative (Pasha picked weaker team)
> - Actually: `opponent_avg_skill` = 30, `picked_team_avg_skill` = 55
> - `skill_differential` = 30 − 55 = **−25** ← this is *negative* meaning Pasha picked the *weaker* team (higher skill value = worse)
>
> Wait — let me re-anchor:
>
> - `skill_value`: **0 = best**, **100 = worst**
> - Puck Bunnies: skill 55 (worse)
> - Mighty Quacks: skill 30 (better)
> - Pasha picks **Puck Bunnies** (the underdog)
> - `opponent_avg_skill` (Quacks) = 30
> - `picked_team_avg_skill` (Bunnies) = 55
> - `skill_differential` = `opponent_avg_skill − picked_team_avg_skill` = 30 − 55 = **−25**
>
> Hmm, that's negative. Let me invert the formula to make "upset = positive":
>
> ```
> skill_differential = picked_team_avg_skill - opponent_avg_skill
> # Positive = picked the WORSE team = upset pick
> # Puck Bunnies (55) - Mighty Quacks (30) = +25 → upset pick ✓
> ```

**Corrected formula (canonical):**

```
skill_differential = picked_team_avg_skill − opponent_avg_skill
is_upset_pick      = skill_differential > 0
upset_bonus        = max(0, floor(skill_differential × 0.5))  if is_upset_pick else 0
```

**Final example:**

| Field | Value |
|---|---|
| Picked team (Puck Bunnies) avg skill | 55 |
| Opponent (Mighty Quacks) avg skill | 30 |
| skill_differential | 55 − 30 = **+25** |
| is_upset_pick | ✅ True |
| base_points | 10 |
| upset_bonus | floor(25 × 0.5) = **12** |
| pre_multiplier | 10 + 12 = **22** |
| confidence | 3x |
| **total_points** | 22 × 3 = **66** |

Puck Bunnies wins. Pasha earns **66 points**. 🎉

---

### Grading Service

```python
# app/services/result_grader.py

import math
from datetime import datetime, timezone
from sqlalchemy import and_
from app.db import HBSession, PredSession
from hockey_blast_common_lib.models import Game
from app.models import PredPick, PredResult, PredLeague
from app.services.standings_service import update_standings_for_result


FINAL_STATUSES = {"Final", "Final/OT", "Final/SO"}
VOID_STATUSES  = {"Forfeit", "CANCELED"}
UPSET_SCALE    = 0.5


def grade_completed_games():
    """
    Background job. Finds all ungraded picks for completed games and grades them.
    Safe to run multiple times (idempotent via unique constraint on pick_id).
    """
    pred_session = PredSession()
    hb_session = HBSession()

    # Find ungraded picks
    ungraded_picks = (
        pred_session.query(PredPick)
        .outerjoin(PredResult, PredPick.id == PredResult.pick_id)
        .filter(PredResult.id.is_(None))
        .filter(PredPick.is_locked == True)
        .all()
    )

    game_cache = {}

    for pick in ungraded_picks:
        if pick.game_id not in game_cache:
            game_cache[pick.game_id] = (
                hb_session.query(Game).filter(Game.id == pick.game_id).first()
            )
        game = game_cache[pick.game_id]

        if not game or game.status not in FINAL_STATUSES | VOID_STATUSES:
            continue  # Not finished yet

        result = _grade_pick(pick, game, pred_session)
        pred_session.add(result)

        # Update standings
        league = pred_session.query(PredLeague).filter(
            PredLeague.id == pick.league_id
        ).first()
        update_standings_for_result(result, pick, league, pred_session)

    pred_session.commit()


def _grade_pick(pick: PredPick, game: Game, pred_session) -> PredResult:
    league = pred_session.query(PredLeague).filter(
        PredLeague.id == pick.league_id
    ).first()

    result = PredResult(
        pick_id=pick.id,
        game_final_status=game.status,
        graded_at=datetime.now(timezone.utc),
    )

    # Voided games
    if game.status in VOID_STATUSES:
        result.is_correct = False
        result.base_points = 0
        result.upset_bonus_points = 0
        result.pre_multiplier_points = 0
        result.confidence_multiplier = pick.confidence
        result.total_points = 0
        result.actual_winner_team_id = None
        return result

    # Determine winner from goals
    actual_winner = _get_winner(game, pred_session)
    result.actual_winner_team_id = actual_winner
    result.is_correct = (actual_winner == pick.picked_team_id)
    result.confidence_multiplier = pick.confidence

    if not result.is_correct:
        result.base_points = 0
        result.upset_bonus_points = 0
        result.pre_multiplier_points = 0
        result.total_points = 0
        return result

    base = league.correct_pick_base_points if league else 10
    result.base_points = base

    upset_bonus = 0
    if league and league.upset_bonus_enabled and pick.skill_differential is not None:
        diff = float(pick.skill_differential)
        if diff > 0:
            upset_bonus = max(0, math.floor(diff * UPSET_SCALE))
    result.upset_bonus_points = upset_bonus
    result.pre_multiplier_points = base + upset_bonus

    multiplier = pick.confidence if (league and league.confidence_multiplier_enabled) else 1
    result.total_points = result.pre_multiplier_points * multiplier

    return result


def _get_winner(game: Game, pred_session) -> int | None:
    """
    Determine the winning team_id for a final game.
    Uses goal counts from the hockey_blast DB.
    Returns None if no clear winner (shouldn't happen in hockey).
    """
    from hockey_blast_common_lib.models import Goal
    hb_session = HBSession()

    home_goals = (
        hb_session.query(Goal)
        .filter(Goal.game_id == game.id, Goal.team_id == game.home_team_id)
        .count()
    )
    away_goals = (
        hb_session.query(Goal)
        .filter(Goal.game_id == game.id, Goal.team_id == game.away_team_id)
        .count()
    )

    if home_goals > away_goals:
        return game.home_team_id
    elif away_goals > home_goals:
        return game.away_team_id
    else:
        return None  # Tie — void
```

---

## 5. API Design

### Blueprint Registration

```python
# app/__init__.py (Flask app factory)

from flask import Flask
from app.blueprints.auth import auth_bp
from app.blueprints.picks import picks_bp
from app.blueprints.leagues import leagues_bp
from app.blueprints.results import results_bp
from app.blueprints.games import games_bp

def create_app(config=None):
    app = Flask(__name__)
    app.register_blueprint(auth_bp,    url_prefix="/api/auth")
    app.register_blueprint(picks_bp,   url_prefix="/api/picks")
    app.register_blueprint(leagues_bp, url_prefix="/api/leagues")
    app.register_blueprint(results_bp, url_prefix="/api/results")
    app.register_blueprint(games_bp,   url_prefix="/api/games")
    return app
```

### Auth Decorator

```python
# app/auth.py

from functools import wraps
from flask import request, jsonify, g
import jwt  # PyJWT

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token(request)
        if not token:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            payload = _verify_jwt(token)  # validates against Auth0 JWKS
            g.user_sub = payload["sub"]
            g.pred_user = _get_or_create_pred_user(payload)
        except Exception as e:
            return jsonify({"error": "Invalid token", "detail": str(e)}), 401
        return f(*args, **kwargs)
    return decorated
```

---

### `GET /api/games`

Browse upcoming pickable games.

**Query params:**
- `org_id` — filter by organization
- `division_id` — filter by division
- `season_id` — filter by season
- `from_date` — ISO8601 date (default: today)
- `to_date` — ISO8601 date (default: +7 days)
- `page` / `per_page` — pagination

**Response:**
```json
{
  "games": [
    {
      "game_id": 123456,
      "scheduled_start": "2026-03-15T20:00:00Z",
      "lock_deadline": "2026-03-15T20:00:00Z",
      "home_team": { "id": 11, "name": "Puck Bunnies", "avg_skill": 55.2 },
      "away_team": { "id": 22, "name": "Mighty Quacks", "avg_skill": 30.1 },
      "org": { "id": 1, "name": "Sharks Ice" },
      "division": { "id": 5, "name": "Monday Div 3" },
      "is_pickable": true,
      "is_live": false
    }
  ],
  "total": 842,
  "page": 1,
  "per_page": 20
}
```

---

### `GET /api/games/:game_id`

Single game detail with pick context for the authenticated user.

**Response:**
```json
{
  "game_id": 123456,
  "scheduled_start": "2026-03-15T20:00:00Z",
  "home_team": { "id": 11, "name": "Puck Bunnies", "avg_skill": 55.2, "record": "5-3-1" },
  "away_team": { "id": 22, "name": "Mighty Quacks", "avg_skill": 30.1, "record": "8-1-0" },
  "is_pickable": true,
  "user_pick": null
}
```

---

### `POST /api/picks`

Submit or update a pick. Requires auth. Fails if game is locked.

**Request:**
```json
{
  "game_id": 123456,
  "league_id": 7,
  "picked_team_id": 11,
  "confidence": 3
}
```

**Response (201 Created):**
```json
{
  "pick_id": 9901,
  "game_id": 123456,
  "picked_team_id": 11,
  "confidence": 3,
  "is_upset_pick": true,
  "skill_differential": 25.1,
  "projected_points": { "correct": 66, "wrong": 0 },
  "lock_deadline": "2026-03-15T20:00:00Z"
}
```

**Error (409 Conflict):**
```json
{ "error": "PICK_LOCKED", "message": "Pick window has closed (game has started)" }
```

---

### `GET /api/picks`

List the current user's picks.

**Query params:** `league_id`, `status` (`pending|graded|all`), `page`

---

### `DELETE /api/picks/:pick_id`

Retract a pick (only if game not yet locked).

---

### `POST /api/leagues`

Create a new league. Requires auth.

**Request:**
```json
{
  "name": "Monday Warriors 2026",
  "description": "Div 3 Sharks Ice only",
  "scope": "org",
  "org_id": 1,
  "season_id": 42,
  "max_members": 20,
  "upset_bonus_enabled": true,
  "confidence_multiplier_enabled": true
}
```

**Response (201 Created):**
```json
{
  "league_id": 7,
  "name": "Monday Warriors 2026",
  "join_code": "X7KP2MNA",
  "commissioner_id": 42
}
```

---

### `POST /api/leagues/join`

Join a league via join code.

**Request:** `{ "join_code": "X7KP2MNA" }`

---

### `GET /api/leagues/:league_id`

League detail with member count and commissioner info.

---

### `GET /api/leagues/:league_id/standings`

Full leaderboard for a league.

**Response:**
```json
{
  "league_id": 7,
  "league_name": "Monday Warriors 2026",
  "standings": [
    {
      "rank": 1,
      "user": { "id": 42, "display_name": "Pasha", "avatar_url": "..." },
      "total_points": 380,
      "total_picks": 22,
      "correct_picks": 15,
      "pick_accuracy": 68.18,
      "upset_picks_correct": 4,
      "high_conf_correct": 3
    }
  ],
  "last_updated_at": "2026-03-11T04:30:00Z"
}
```

---

### `GET /api/leagues/:league_id/picks`

All picks in a league for a given game (visible after game locks).

**Query params:** `game_id` (required)

> **Privacy note:** Other users' picks are only visible after the game locks. Before lock, you can only see your own pick.

---

### `GET /api/results`

Graded results for the current user.

**Query params:** `league_id`, `page`

---

### `GET /api/leagues/:league_id/picks/mine`

Current user's full pick history within a league.

---

### Error Response Format

All errors return:
```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable description"
}
```

Standard error codes: `UNAUTHORIZED`, `NOT_FOUND`, `PICK_LOCKED`, `ALREADY_PICKED`, `LEAGUE_FULL`, `INVALID_TEAM`, `VALIDATION_ERROR`

---

## 6. Pick-Em UX Flow

> This section describes screens and user journeys — no UI code. Front-end team uses this as spec.

### Screen Map

```
Landing / Home
  ├── Sign In (Auth0 modal)
  └── [Authenticated]
      ├── My Dashboard
      │   ├── My Leagues (list)
      │   ├── Upcoming Picks To Make (action items)
      │   └── Recent Results
      ├── Game Browser
      │   ├── Filter by Org / Division / Date
      │   ├── Game Card
      │   │   ├── Pick Widget (if pickable)
      │   │   └── Lock Countdown Timer
      │   └── Locked Game Card (pick revealed after lock)
      ├── League Detail
      │   ├── Standings Leaderboard
      │   ├── My Picks Tab
      │   └── All Picks Tab (post-lock)
      ├── League Create / Join
      └── Profile / Settings
          └── Link HB Profile
```

---

### Flow 1: First-Time Onboarding

1. User lands on homepage — sees marketing copy + "Sign In" CTA
2. Clicks Sign In → Auth0 modal → chooses Google/Apple/Facebook
3. Auth0 callback → account created (`PredUser` upserted)
4. Redirected to **onboarding wizard**:
   - Step 1: Set display name (pre-filled from OAuth)
   - Step 2: "Create a league or join one?" → two CTAs
   - Step 3 (optional): Link Hockey Blast profile (`hb_human_id`)
5. Lands on Dashboard

---

### Flow 2: Creating a League

1. From Dashboard → "Create League"
2. Form:
   - League name
   - Description (optional)
   - Scope: All Orgs / Specific Org / Specific Division
   - Season filter (optional)
   - Scoring options (toggles: upset bonus, confidence multiplier)
   - Max members
3. Submit → league created → commissioner sees league detail page
4. Share join code / share link (`/join/X7KP2MNA`)

---

### Flow 3: Joining a League

1. User receives link or code
2. `/join/X7KP2MNA` → pre-filled join page or "Sign In first" gate
3. Confirms join → redirected to league leaderboard (empty, just joined)

---

### Flow 4: Making a Pick

1. User visits **Game Browser** (or "Picks To Make" shortcut on Dashboard)
2. Sees game card:
   ```
   ┌─────────────────────────────────────────┐
   │  🏒 Monday Div 3 — Sharks Ice           │
   │  Mar 15, 2026 8:00 PM PST               │
   │  🔒 Locks in 3h 22m                     │
   │                                          │
   │  Puck Bunnies      vs    Mighty Quacks   │
   │  Avg Skill: 55 ↓        Avg Skill: 30 ↑ │
   │  (underdog)             (favorite)       │
   │                                          │
   │  [ Pick Puck Bunnies ]  [ Pick Quacks ]  │
   └─────────────────────────────────────────┘
   ```
   > ↑ = better team (lower skill value), ↓ = weaker team
3. User clicks "Pick Puck Bunnies"
4. **Confidence selector** appears:
   ```
   How confident are you?
   [ 1x — Safe bet ]  [ 2x — Pretty sure ]  [ 3x — Bet the farm ]
   ```
5. User selects **3x**
6. **Points preview** shown:
   ```
   If correct:  66 pts  (upset bonus: +12, confidence: ×3)
   If wrong:     0 pts
   ```
7. "Confirm Pick" button → POST /api/picks
8. Card updates to show locked-in pick with countdown timer

---

### Flow 5: Post-Game Result

1. Game finishes (grader job runs)
2. User returns to game card — now shows result:
   ```
   ✅ Puck Bunnies won! You picked correctly.
   You earned 66 points (upset bonus: +12, 3x confidence)
   ```
   or
   ```
   ❌ Mighty Quacks won. Better luck next time.
   You earned 0 points.
   ```
3. Leaderboard refreshes — rank may change

---

### Flow 6: Viewing the Leaderboard

1. User taps "League" → Standings tab
2. Table: Rank | Player | Points | W/L | Accuracy | 🔥 Streak (stretch)
3. Current user's row highlighted
4. "All Picks" tab: shows all league members' picks for each game — **only after game lock**

---

### Pick Visibility Rules

| When | My Pick | Others' Picks |
|---|---|---|
| Before game lock | Visible to me only | Hidden |
| After game lock, before result | Visible to all in league | Visible (no result yet) |
| After result graded | Visible to all | Visible with result |

---

## 7. Implementation Phases

### Phase 0: Skeleton (Week 1–2)

- [ ] Repo scaffolded (`hockey-blast-predictions`)
- [ ] Dual DB connection working (`HBSession` + `PredSession`)
- [ ] Auth0 integration: login/logout, JWT validation, `@require_auth` decorator
- [ ] `PredUser` model + upsert on login
- [ ] Alembic configured, initial migration
- [ ] Health check endpoint `GET /api/health`
- [ ] CI pipeline (GitHub Actions: lint, test, migrate)

### Phase 1: MVP Pick-Em (Week 3–5)

**Goal:** One user can pick a game and see a result.

- [ ] `PredLeague`, `PredLeagueMember` models + migrations
- [ ] `PredPick` model + migrations
- [ ] `PredResult`, `PredLeagueStandings` models + migrations
- [ ] `GET /api/games` — game browser with skill data
- [ ] `POST /api/picks` — submit pick with lock check + skill snapshot
- [ ] `DELETE /api/picks/:id` — retract pick
- [ ] Background grader job (`grade_completed_games`)
- [ ] `GET /api/results` — view graded picks
- [ ] `POST /api/leagues` — create league
- [ ] `POST /api/leagues/join` — join via code
- [ ] `GET /api/leagues/:id/standings` — basic leaderboard
- [ ] Minimal frontend (functional, not polished) — game list, pick widget, standings table

**MVP is done when:** 5 friends can be in a league, pick games all week, and see a leaderboard on Sunday.

### Phase 2: Engagement Layer (Week 6–8)

- [ ] Dashboard: "Picks to make" widget (upcoming games in your leagues, unpicked)
- [ ] Pick history page with point breakdown per pick
- [ ] Lock countdown timer (client-side JS, synced to server time)
- [ ] Post-lock reveal: see everyone's picks side-by-side
- [ ] Email notifications: "2 games lock tonight — make your picks!" (SendGrid)
- [ ] League commissioner tools: edit name/description, remove members
- [ ] Link Hockey Blast profile (`hb_human_id` lookup by name/email)
- [ ] Mobile-responsive layout pass

### Phase 3: Polish & Social (Week 9–12)

- [ ] Pick streak tracking (consecutive correct picks)
- [ ] Upset badge / achievement system
- [ ] Season summary: "You went 68% correct with 4 upsets!"
- [ ] Public leaderboard opt-in (browse public leagues)
- [ ] Shareable pick card (image generation or OG meta)
- [ ] Push notifications (Web Push API) for lock warnings + results
- [ ] Commissioner: create custom game pools (cherry-pick specific games)

### Phase 4: Stretch Goals

- [ ] Multiple picks per game (home win / away win / OT/SO outcome)
- [ ] Survivor pool mode (pick one team per week, eliminated if wrong)
- [ ] Live game view with pick reveal and live scoring
- [ ] Season-long prediction: division champion, top scorer
- [ ] Admin dashboard for HB staff: monitor all leagues, manual result override

---

## 8. Repo Structure

```
hockey-blast-predictions/
│
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── config.py                # Config classes (dev/staging/prod)
│   ├── db.py                    # Dual DB sessions (HBSession, PredSession)
│   ├── auth.py                  # JWT validation, @require_auth decorator
│   │
│   ├── models/
│   │   ├── __init__.py          # Re-exports all models
│   │   ├── base.py              # PredBase = declarative_base()
│   │   ├── pred_user.py
│   │   ├── pred_league.py
│   │   ├── pred_league_member.py
│   │   ├── pred_pick.py
│   │   ├── pred_result.py
│   │   └── pred_league_standings.py
│   │
│   ├── blueprints/
│   │   ├── auth.py              # /api/auth/...
│   │   ├── games.py             # /api/games/...
│   │   ├── picks.py             # /api/picks/...
│   │   ├── leagues.py           # /api/leagues/...
│   │   └── results.py           # /api/results/...
│   │
│   ├── services/
│   │   ├── lock_checker.py      # is_game_pickable()
│   │   ├── skill_snapshot.py    # get_team_avg_skill()
│   │   ├── result_grader.py     # grade_completed_games()
│   │   ├── standings_service.py # update_standings_for_result()
│   │   └── user_service.py      # get_or_create_pred_user()
│   │
│   ├── jobs/
│   │   ├── __init__.py
│   │   └── scheduler.py         # APScheduler setup
│   │
│   └── utils/
│       ├── pagination.py
│       ├── datetime_utils.py
│       └── response.py          # Standardized JSON responses
│
├── migrations/
│   ├── env.py                   # Alembic env (points to predictions_db only)
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial.py
│
├── tests/
│   ├── conftest.py              # pytest fixtures, test DB setup
│   ├── unit/
│   │   ├── test_scoring.py      # Pure scoring math
│   │   ├── test_lock_checker.py
│   │   └── test_skill_snapshot.py
│   └── integration/
│       ├── test_picks_api.py
│       ├── test_leagues_api.py
│       └── test_grader.py
│
├── frontend/                    # Optional: React SPA or Jinja2 templates
│   └── (TBD based on tech decision — see Open Questions)
│
├── .github/
│   └── workflows/
│       ├── ci.yml               # lint + test on PR
│       └── deploy.yml           # deploy on main merge
│
├── .env.example                 # Required env vars documented
├── .flake8
├── pyproject.toml               # Project metadata + tool config
├── requirements.txt
├── requirements-dev.txt
├── alembic.ini
├── wsgi.py                      # Gunicorn entry point
└── README.md
```

---

## 9. Key Dependencies

| Package | Version | Purpose |
|---|---|---|
| `flask` | `3.1.x` | Web framework |
| `sqlalchemy` | `2.0.x` | ORM — **must be 2.x** for modern query style |
| `alembic` | `1.13.x` | DB migrations |
| `psycopg2-binary` | `2.9.x` | PostgreSQL adapter |
| `hockey_blast_common_lib` | `latest` | Read access to HB models |
| `authlib` | `1.3.x` | Auth0 OIDC / OAuth2 client |
| `PyJWT` | `2.8.x` | JWT decode + verification |
| `cryptography` | `42.x` | JWT RS256 key handling |
| `flask-cors` | `4.x` | CORS headers for SPA frontend |
| `APScheduler` | `3.10.x` | Background grader + lock jobs |
| `python-dotenv` | `1.0.x` | `.env` loading |
| `pydantic` | `2.x` | Request validation schemas |
| `gunicorn` | `21.x` | Production WSGI server |
| `pytest` | `7.x` | Test framework |
| `pytest-flask` | `1.3.x` | Flask test client fixtures |
| `factory-boy` | `3.3.x` | Test data factories |
| `black` | `24.x` | Code formatter |
| `flake8` | `7.x` | Linter |
| `mypy` | `1.x` | Type checking |

**Why SQLAlchemy 2.x?**  
Unified `session.execute(select(...))` style is cleaner than legacy `session.query()`. New repos should use 2.x style throughout. If `hockey_blast_common_lib` uses 1.x query patterns, that's fine — isolate it behind `HBSession`.

**Why APScheduler over Celery?**  
For v1 with modest load, APScheduler embedded in the Flask process is simpler (no Redis, no worker processes). Upgrade path to Celery is clear if/when needed.

**Why Pydantic 2.x for validation?**  
Pydantic v2 is dramatically faster and has a clean Flask integration story. Better than WTForms or marshmallow for API-first JSON validation.

---

## 10. Open Questions for Pasha

These need answers before or during Phase 1 development:

### Database & Infrastructure

1. **Separate DB or same Postgres instance?** The design assumes `predictions_db` is a separate logical database on the same Postgres instance as `hockey_blast`. Is that correct, or do you want a completely separate RDS/Render instance?

2. **`hockey_blast_common_lib` — what's the actual pip install path?** Git+SSH from a private repo? Local path install during dev? PyPI? The `requirements.txt` needs this.

3. **What fields does `Game` have exactly?** Specifically: `game_date_time` (is it timezone-aware?), `home_team_id`, `away_team_id`, `status`, `live_time`. I need the exact field names to avoid guessing.

4. **Does `org_stats_skater` have a `team_id` column?** The skill snapshot service assumes it does. If skill data is per-human (not per-team), we need to join through `GameRoster` to get team avg skill — which changes the snapshot logic significantly.

### Scoring & Gameplay

5. **Forfeit handling:** Should a forfeit give the "winning" team (the one that showed up) full credit? Or void all picks for that game? I defaulted to void — let me know if you want otherwise.

6. **Confidence multiplier — should wrong picks have *negative* points?** The current design gives 0 for wrong picks. Some leagues do `-confidence` penalty (e.g., 3x wrong = −3 pts). That changes the stakes dramatically. Your call.

7. **UPSET_SCALE = 0.5** — does this feel right? With a 25-point skill differential, the upset bonus is +12 points on top of the 10 base. Want to playtest this number before launch.

8. **Pick window:** Should picks lock exactly at game start, or N minutes before (e.g., 15 min buffer)? A small buffer prevents picks on games that are already live but whose status hasn't updated yet.

### Product & UX

9. **Frontend tech:** React SPA (API-only Flask backend) vs. Jinja2 + HTMX (Flask renders HTML)? Both are viable. React = better interactive experience, more work. HTMX = faster to ship MVP, good enough for leaderboards.

10. **Who gets to see picks before lock?** Currently: nobody else sees your pick until the game locks. Should commissioners have override visibility? (Probably not, but worth deciding.)

11. **League privacy:** Can non-members see a public league's standings? Or is all data private to members only?

12. **Multiple leagues per game:** A user can be in multiple leagues and make separate picks per league for the same game. Is that intended? (Yes per the data model.) Should confidence be set per-league or shared?

13. **Hosting:** Where does this deploy? Same server as hockey-blast.com? Render? Railway? Fly.io? Affects whether we need multi-DB config or can share a Postgres instance directly.

### Auth & Users

14. **Auth0 tenant:** New tenant or add an application to the existing HB Auth0 tenant (if one exists)?

15. **HB profile linking:** Should this be opt-in (user manually links their HB account) or automatic (match by email on first login)? Auto-match is convenient but risky if emails don't match.

---

*Document ends. Ready for review.*

---

**Next Steps:**
1. Pasha reviews and answers Open Questions
2. Dev sets up repo, installs skeleton, verifies dual-DB connection
3. Alembic initial migration run
4. Phase 1 sprint begins

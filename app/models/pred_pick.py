"""
PredPick — one user's prediction for one game within one league.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class PredPick(PredBase):
    """
    A single pick: user selects the winner of an upcoming game with a confidence level.

    Cross-DB references (no FK constraints — data lives in hockey_blast DB):
        game_id           → hockey_blast.games.id
        picked_team_id    → hockey_blast.teams.id
        home_team_id      → hockey_blast.teams.id
        away_team_id      → hockey_blast.teams.id

    Locking is enforced in pick_service.py, not here.
    """

    __tablename__ = "pred_picks"
    __table_args__ = (
        # One pick per user per game per league
        UniqueConstraint("user_id", "game_id", "league_id", name="uq_pick_user_game_league"),
        # Confidence must be 1, 2, or 3
        CheckConstraint("confidence IN (1, 2, 3)", name="ck_confidence_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ── Who picked ────────────────────────────────────────────────────────────
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_users.id"), nullable=False, index=True
    )
    league_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_leagues.id"), nullable=False, index=True
    )

    # ── What game (denormalized for query performance) ────────────────────────
    game_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    game_scheduled_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    home_team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    away_team_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── The pick itself ───────────────────────────────────────────────────────
    picked_team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Must be home_team_id or away_team_id — enforced in pick_service.

    confidence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 1 = 1x, 2 = 2x, 3 = 3x

    wager: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Optional paper-money wager (1–500). None = no wager placed.

    # ── Sportsbook odds snapshot (captured at pick submission time) ───────────
    odds_at_pick: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    # Odds multiplier at the time of pick submission (e.g. 1.85)

    effective_wager: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # wager × confidence — total pts at risk

    potential_payout: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # floor(effective_wager × odds_at_pick) — max pts to win if correct

    # ── Skill snapshot (captured at pick submission time) ─────────────────────
    # skill_value: 0 = elite, 100 = worst
    home_team_avg_skill: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    away_team_avg_skill: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    picked_team_avg_skill: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    opponent_avg_skill: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    skill_differential: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    # = picked_team_avg_skill - opponent_avg_skill
    # Positive → picked the underdog (worse team) → upset pick ✓
    # Negative → picked the favorite

    is_upset_pick: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True when skill_differential > 0 (picked the weaker team)

    # ── Lock state ────────────────────────────────────────────────────────────
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Set True by pick_service when game_scheduled_start passes.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    user: Mapped["PredUser"] = relationship("PredUser", back_populates="picks")
    result: Mapped["PredResult | None"] = relationship(
        "PredResult", back_populates="pick", uselist=False
    )

    def __repr__(self) -> str:
        return (
            f"<PredPick id={self.id} user={self.user_id} game={self.game_id} "
            f"team={self.picked_team_id} conf={self.confidence}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "league_id": self.league_id,
            "game_id": self.game_id,
            "game_scheduled_start": (
                self.game_scheduled_start.isoformat() if self.game_scheduled_start else None
            ),
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "picked_team_id": self.picked_team_id,
            "confidence": self.confidence,
            "wager": self.wager,
            "odds_at_pick": float(self.odds_at_pick) if self.odds_at_pick is not None else None,
            "effective_wager": self.effective_wager,
            "potential_payout": self.potential_payout,
            "skill_differential": (
                float(self.skill_differential) if self.skill_differential is not None else None
            ),
            "is_upset_pick": self.is_upset_pick,
            "is_locked": self.is_locked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            # Computed: game started but not graded yet = "live", past start with result = "graded", else "pending"
            "is_started": (
                self.game_scheduled_start is not None and
                self.game_scheduled_start <= datetime.now(timezone.utc)
            ),
        }

"""
PredLeagueStandings — materialized per-user standings within a league.
Updated by standings_service.refresh_standings() after each grading batch.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class PredLeagueStandings(PredBase):
    """
    Rolling standings for a user within a league.
    Always derived from PredResult rows — never update directly.
    Use standings_service.refresh_standings() to recalculate.
    """

    __tablename__ = "pred_league_standings"
    __table_args__ = (
        UniqueConstraint("user_id", "league_id", name="uq_standings_user_league"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_users.id"), nullable=False, index=True
    )
    league_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_leagues.id"), nullable=False, index=True
    )

    # ── Cumulative stats ───────────────────────────────────────────────────────
    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_picks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_picks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    upset_picks_correct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_conf_correct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Count of confidence=3 picks that were correct.

    pick_accuracy: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0, nullable=False)
    # correct_picks / total_picks × 100 (percentage, excluding voided picks)

    # ── Rank ──────────────────────────────────────────────────────────────────
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 1 = top of leaderboard; null until at least one game is graded.

    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    user: Mapped["PredUser"] = relationship("PredUser")
    league: Mapped["PredLeague"] = relationship("PredLeague", back_populates="standings")

    def __repr__(self) -> str:
        return (
            f"<PredLeagueStandings user={self.user_id} league={self.league_id} "
            f"pts={self.total_points} rank={self.rank}>"
        )

    def to_dict(self, include_user: bool = False) -> dict:
        data: dict = {
            "rank": self.rank,
            "user_id": self.user_id,
            "league_id": self.league_id,
            "total_points": self.total_points,
            "total_picks": self.total_picks,
            "correct_picks": self.correct_picks,
            "pick_accuracy": float(self.pick_accuracy) if self.pick_accuracy else 0.0,
            "upset_picks_correct": self.upset_picks_correct,
            "high_conf_correct": self.high_conf_correct,
            "last_updated_at": (
                self.last_updated_at.isoformat() if self.last_updated_at else None
            ),
        }
        if include_user and self.user:
            data["user"] = self.user.to_dict()
        return data

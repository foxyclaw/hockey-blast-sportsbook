"""
FantasyStandings — aggregate points per manager in a fantasy league.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class FantasyStandings(PredBase):
    __tablename__ = "fantasy_standings"
    __table_args__ = (
        UniqueConstraint("league_id", "user_id", name="uq_fantasy_standings_league_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("fantasy_leagues.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("pred_users.id"), nullable=False)
    total_points: Mapped[float] = mapped_column(Numeric(8, 1), nullable=False, default=0)
    week_points: Mapped[float] = mapped_column(Numeric(8, 1), nullable=False, default=0)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    league: Mapped["FantasyLeague"] = relationship("FantasyLeague", back_populates="standings")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "league_id": self.league_id,
            "user_id": self.user_id,
            "total_points": float(self.total_points),
            "week_points": float(self.week_points),
            "rank": self.rank,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<FantasyStandings id={self.id} league_id={self.league_id} user_id={self.user_id}>"


from app.models.fantasy_league import FantasyLeague  # noqa: E402

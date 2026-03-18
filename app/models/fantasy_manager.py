"""
FantasyManager — a user's entry in a fantasy league (their team).
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class FantasyManager(PredBase):
    __tablename__ = "fantasy_managers"
    __table_args__ = (
        UniqueConstraint("league_id", "user_id", name="uq_fantasy_managers_league_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("fantasy_leagues.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("pred_users.id"), nullable=False)
    team_name: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compensatory_picks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    league: Mapped["FantasyLeague"] = relationship("FantasyLeague", back_populates="managers")
    user: Mapped["PredUser"] = relationship("PredUser", foreign_keys=[user_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "league_id": self.league_id,
            "user_id": self.user_id,
            "team_name": self.team_name,
            "draft_position": self.draft_position,
            "compensatory_picks": self.compensatory_picks,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }

    def __repr__(self) -> str:
        return f"<FantasyManager id={self.id} league_id={self.league_id} user_id={self.user_id}>"


from app.models.fantasy_league import FantasyLeague  # noqa: E402
from app.models.pred_user import PredUser  # noqa: E402

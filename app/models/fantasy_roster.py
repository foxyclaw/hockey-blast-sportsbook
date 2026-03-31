"""
FantasyRoster — a player on a manager's fantasy team.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class FantasyRoster(PredBase):
    __tablename__ = "fantasy_roster"
    __table_args__ = (
        UniqueConstraint("league_id", "hb_human_id", name="uq_fantasy_roster_league_human"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("fantasy_leagues.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("pred_users.id"), nullable=False)
    hb_human_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_goalie: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_ref: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    round_picked: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pick_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drafted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    league: Mapped["FantasyLeague"] = relationship("FantasyLeague", back_populates="roster")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "league_id": self.league_id,
            "user_id": self.user_id,
            "hb_human_id": self.hb_human_id,
            "is_goalie": self.is_goalie,
            "is_ref": self.is_ref,
            "round_picked": self.round_picked,
            "pick_number": self.pick_number,
            "drafted_at": self.drafted_at.isoformat() if self.drafted_at else None,
        }

    def __repr__(self) -> str:
        return f"<FantasyRoster id={self.id} league_id={self.league_id} human_id={self.hb_human_id}>"


from app.models.fantasy_league import FantasyLeague  # noqa: E402

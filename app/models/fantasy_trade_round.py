"""
FantasyTradeRound — a mid-season trade round for an active fantasy league.

The league creator initiates a round. Managers take turns in ascending fantasy-
points order (lowest FP goes first). On their turn a manager may release one
player and acquire one available player of the SAME type (skater/goalie/ref), or
skip. Managers who miss their turn get a second-chance pass (round-robin) after
everyone else has gone; then the round completes.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase

# Status values
TRADE_ROUND_ACTIVE = "active"
TRADE_ROUND_COMPLETED = "completed"
TRADE_ROUND_CANCELED = "canceled"


class FantasyTradeRound(PredBase):
    __tablename__ = "fantasy_trade_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(
        Integer, sa.ForeignKey("fantasy_leagues.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TRADE_ROUND_ACTIVE)
    # Per-turn time window in hours (defaults to 24 like the draft).
    pick_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    created_by: Mapped[int | None] = mapped_column(
        Integer, sa.ForeignKey("pred_users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    league: Mapped["FantasyLeague"] = relationship("FantasyLeague")
    turns: Mapped[list["FantasyTradeTurn"]] = relationship(
        "FantasyTradeTurn", back_populates="round", lazy="dynamic"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "league_id": self.league_id,
            "status": self.status,
            "pick_hours": self.pick_hours,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def __repr__(self) -> str:
        return f"<FantasyTradeRound id={self.id} league_id={self.league_id} status={self.status!r}>"


from app.models.fantasy_league import FantasyLeague  # noqa: E402
from app.models.fantasy_trade_turn import FantasyTradeTurn  # noqa: E402

"""
FantasyDraftQueue — ordered list of draft picks for a fantasy league snake draft.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class FantasyDraftQueue(PredBase):
    __tablename__ = "fantasy_draft_queue"
    __table_args__ = (
        UniqueConstraint("league_id", "overall_pick", name="uq_fantasy_draft_queue_league_pick"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("fantasy_leagues.id"), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    pick_in_round: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("pred_users.id"), nullable=False)
    hb_human_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_goalie_pick: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_ref_pick: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    picked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    league: Mapped["FantasyLeague"] = relationship("FantasyLeague", back_populates="draft_queue")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "league_id": self.league_id,
            "round": self.round,
            "pick_in_round": self.pick_in_round,
            "overall_pick": self.overall_pick,
            "user_id": self.user_id,
            "hb_human_id": self.hb_human_id,
            "is_skipped": self.is_skipped,
            "is_goalie_pick": self.is_goalie_pick,
            "is_ref_pick": self.is_ref_pick,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "picked_at": self.picked_at.isoformat() if self.picked_at else None,
        }

    def __repr__(self) -> str:
        return f"<FantasyDraftQueue id={self.id} pick={self.overall_pick} user_id={self.user_id}>"


from app.models.fantasy_league import FantasyLeague  # noqa: E402

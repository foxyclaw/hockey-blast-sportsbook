"""
FantasyManagerQueue — per-manager priority wishlist for the snake draft.

Each row represents one player a manager wants to draft, in their preferred order.
During autopick (or when it's their turn and they've set a queue), the system
picks the first available player from this list.
"""

import sqlalchemy as sa
from sqlalchemy import Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import PredBase


class FantasyManagerQueue(PredBase):
    __tablename__ = "fantasy_manager_queue"
    __table_args__ = (
        UniqueConstraint("league_id", "user_id", "hb_human_id", name="uq_fmq_league_user_human"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("fantasy_leagues.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("pred_users.id"), nullable=False)
    hb_human_id: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 = top priority

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "league_id": self.league_id,
            "user_id": self.user_id,
            "hb_human_id": self.hb_human_id,
            "position": self.position,
        }

    def __repr__(self) -> str:
        return f"<FantasyManagerQueue league={self.league_id} user={self.user_id} human={self.hb_human_id} pos={self.position}>"

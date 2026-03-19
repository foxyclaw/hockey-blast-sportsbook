"""
PredSubRequest — a captain's request for subs for a specific game.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class PredSubRequest(PredBase):
    __tablename__ = "pred_sub_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hb_team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    captain_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_users.id"), nullable=False
    )
    goalies_needed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skaters_needed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sub_fee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # sub_fee in cents (0 = free, 1500 = $15.00)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    captain: Mapped["PredUser"] = relationship("PredUser")
    responses: Mapped[list["PredSubResponse"]] = relationship(
        "PredSubResponse", back_populates="request"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "game_id": self.game_id,
            "hb_team_id": self.hb_team_id,
            "captain_user_id": self.captain_user_id,
            "goalies_needed": self.goalies_needed,
            "skaters_needed": self.skaters_needed,
            "sub_fee": self.sub_fee,
            "message": self.message,
            "status": self.status,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "created_at": self.created_at.isoformat(),
        }

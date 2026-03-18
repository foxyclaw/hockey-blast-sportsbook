"""
PredSubResponse — a player's response to a sub request.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class PredSubResponse(PredBase):
    __tablename__ = "pred_sub_responses"
    __table_args__ = (UniqueConstraint("request_id", "user_id", name="uq_sub_response"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_sub_requests.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="interested", nullable=False)
    responded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    request: Mapped["PredSubRequest"] = relationship("PredSubRequest", back_populates="responses")
    user: Mapped["PredUser"] = relationship("PredUser")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "status": self.status,
            "responded_at": self.responded_at.isoformat(),
        }

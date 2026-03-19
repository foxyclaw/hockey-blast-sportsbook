"""
PredUserCaptainClaim — records teams where a user claims to be (or have been) captain.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class PredUserCaptainClaim(PredBase):
    __tablename__ = "pred_user_captain_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_users.id"), nullable=False, index=True
    )
    team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    team_name: Mapped[str] = mapped_column(String(128), nullable=False)
    org_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_captain_user_team"),
    )

    user: Mapped["PredUser"] = relationship("PredUser", back_populates="captain_claims")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "team_id": self.team_id,
            "team_name": self.team_name,
            "org_name": self.org_name,
            "is_active": self.is_active,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
        }

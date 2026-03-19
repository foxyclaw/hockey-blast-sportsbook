"""
PredRosterInvite — a captain's invite to a free agent to join their team.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class PredRosterInvite(PredBase):
    __tablename__ = "pred_roster_invites"
    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", "hb_team_id", name="uq_roster_invite"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_users.id"), nullable=False
    )
    to_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_users.id"), nullable=False
    )
    hb_team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    team_name: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    roster_fee_full: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    roster_fee_half: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # fees in cents (0 = free, 35000 = $350.00)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    from_user: Mapped["PredUser"] = relationship("PredUser", foreign_keys=[from_user_id])
    to_user: Mapped["PredUser"] = relationship("PredUser", foreign_keys=[to_user_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_user_id": self.from_user_id,
            "to_user_id": self.to_user_id,
            "hb_team_id": self.hb_team_id,
            "team_name": self.team_name,
            "message": self.message,
            "roster_fee_full": self.roster_fee_full,
            "roster_fee_half": self.roster_fee_half,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

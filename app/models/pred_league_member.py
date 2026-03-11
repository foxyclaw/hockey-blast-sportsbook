"""
PredLeagueMember — junction table linking users to leagues with roles.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class MemberRole(enum.Enum):
    COMMISSIONER = "commissioner"
    MEMBER = "member"


class PredLeagueMember(PredBase):
    """
    Membership record for a user in a league.
    Unique constraint on (user_id, league_id) prevents duplicate membership.
    """

    __tablename__ = "pred_league_members"
    __table_args__ = (
        UniqueConstraint("user_id", "league_id", name="uq_user_league"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_users.id"), nullable=False, index=True
    )
    league_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_leagues.id"), nullable=False, index=True
    )

    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole), default=MemberRole.MEMBER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Soft-delete: set is_active=False when user leaves league.

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    user: Mapped["PredUser"] = relationship("PredUser", back_populates="league_memberships")
    league: Mapped["PredLeague"] = relationship("PredLeague", back_populates="members")

    def __repr__(self) -> str:
        return f"<PredLeagueMember user={self.user_id} league={self.league_id} role={self.role}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "league_id": self.league_id,
            "role": self.role.value,
            "is_active": self.is_active,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }

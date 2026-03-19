"""
PredUserPreferences — per-user player profile preferences.
One row per user (unique on user_id).
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class PredUserPreferences(PredBase):
    __tablename__ = "pred_user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pred_users.id"), unique=True, nullable=False, index=True
    )
    skill_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_free_agent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wants_to_sub: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    interested_location_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    skill_level_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    user: Mapped["PredUser"] = relationship("PredUser", back_populates="preferences")

    def to_dict(self) -> dict:
        return {
            "skill_level": self.skill_level,
            "is_free_agent": self.is_free_agent,
            "wants_to_sub": self.wants_to_sub,
            "notify_email": self.notify_email,
            "notify_phone": self.notify_phone,
            "interested_location_ids": self.interested_location_ids or [],
            "skill_level_comment": self.skill_level_comment,
        }

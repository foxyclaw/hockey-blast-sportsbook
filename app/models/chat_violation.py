"""ChatViolation — tracks off-topic abuse per user with exponential disable."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import PredBase


class ChatViolation(PredBase):
    __tablename__ = "chat_violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    violation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_violation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    disabled_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def is_currently_disabled(self) -> bool:
        if self.disabled_until is None:
            return False
        return datetime.now(timezone.utc) < self.disabled_until

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "violation_count": self.violation_count,
            "last_violation_at": self.last_violation_at.isoformat() if self.last_violation_at else None,
            "disabled_until": self.disabled_until.isoformat() if self.disabled_until else None,
            "is_disabled": self.is_currently_disabled(),
        }

"""ChatMessage — stores every AI chat query + answer for analysis."""
import json
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import PredBase


class ChatMessage(PredBase):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    iterations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_off_topic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    feedback: Mapped[list["ChatFeedback"]] = relationship(
        "ChatFeedback", back_populates="message", lazy="dynamic"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "query": self.query,
            "answer": self.answer,
            "tools_used": self.tools_used or [],
            "iterations": self.iterations,
            "is_off_topic": self.is_off_topic,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

"""SiteEvent — lightweight fire-and-forget activity log."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db import PredBase

# Event types
VISIT = "visit"   # page/app load
PICK  = "pick"    # pick submitted
CHAT  = "chat"    # chat message sent


class SiteEvent(PredBase):
    __tablename__ = "site_events"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str]      = mapped_column(String(32), nullable=False, index=True)
    user_id:    Mapped[int|None] = mapped_column(Integer, nullable=True, index=True)
    ip_address: Mapped[str|None] = mapped_column(String(45), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

"""
FantasyLeague — a fantasy hockey league backed by a real HB level.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class FantasyLeague(PredBase):
    __tablename__ = "fantasy_leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    level_id: Mapped[int] = mapped_column(Integer, nullable=False)
    level_name: Mapped[str] = mapped_column(String(64), nullable=False)
    hb_league_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # HB League (rink/program), e.g. SharksIce SJ = 2
    hb_season_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # HB Season for scoring/pool; NULL = use latest
    org_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    season_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="forming")
    max_managers: Mapped[int] = mapped_column(Integer, nullable=False)
    roster_skaters: Mapped[int] = mapped_column(Integer, nullable=False)
    roster_goalies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    draft_pick_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, sa.ForeignKey("pred_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    draft_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    draft_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    draft_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    season_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    join_code: Mapped[str | None] = mapped_column(String(12), nullable=True)

    # Relationships
    managers: Mapped[list["FantasyManager"]] = relationship(
        "FantasyManager", back_populates="league", lazy="dynamic"
    )
    roster: Mapped[list["FantasyRoster"]] = relationship(
        "FantasyRoster", back_populates="league", lazy="dynamic"
    )
    draft_queue: Mapped[list["FantasyDraftQueue"]] = relationship(
        "FantasyDraftQueue", back_populates="league", lazy="dynamic"
    )
    standings: Mapped[list["FantasyStandings"]] = relationship(
        "FantasyStandings", back_populates="league", lazy="dynamic"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "level_id": self.level_id,
            "level_name": self.level_name,
            "hb_league_id": self.hb_league_id,
            "hb_season_id": self.hb_season_id,
            "org_id": self.org_id,
            "season_label": self.season_label,
            "status": self.status,
            "max_managers": self.max_managers,
            "roster_skaters": self.roster_skaters,
            "roster_goalies": self.roster_goalies,
            "draft_pick_hours": self.draft_pick_hours,
            "settings": self.settings,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "draft_started_at": self.draft_started_at.isoformat() if self.draft_started_at else None,
            "draft_opens_at": self.draft_opens_at.isoformat() if self.draft_opens_at else None,
            "draft_closes_at": self.draft_closes_at.isoformat() if self.draft_closes_at else None,
            "season_starts_at": self.season_starts_at.isoformat() if self.season_starts_at else None,
            "is_private": self.is_private,
            "join_code": self.join_code,
        }

    def __repr__(self) -> str:
        return f"<FantasyLeague id={self.id} name={self.name!r} status={self.status!r}>"


# Avoid circular import — import siblings here
from app.models.fantasy_manager import FantasyManager  # noqa: E402
from app.models.fantasy_roster import FantasyRoster  # noqa: E402
from app.models.fantasy_draft_queue import FantasyDraftQueue  # noqa: E402
from app.models.fantasy_standings import FantasyStandings  # noqa: E402

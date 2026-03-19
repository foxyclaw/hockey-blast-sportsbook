"""
PredLeague — a private pick-em league with members and a game scope.
"""

import enum
import secrets
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class LeagueScope(enum.Enum):
    """Which games this league covers."""

    ALL_ORGS = "all_orgs"
    ORG = "org"
    DIVISION = "division"
    CUSTOM = "custom"  # Stretch goal: admin picks individual games


class PredLeague(PredBase):
    """
    A pick-em league. Created by a commissioner; joined via a short join code.
    """

    __tablename__ = "pred_leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    season_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Human-readable season label, e.g. "2024-25". Display-only; not a FK.

    join_code: Mapped[str] = mapped_column(
        String(16),
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(8).upper()[:8],
    )
    # 8-char alphanumeric code for joining. e.g. "X7KP2MNA"

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Public leagues appear in a browse listing (stretch goal).

    # ── Game scope ─────────────────────────────────────────────────────────────
    scope: Mapped[LeagueScope] = mapped_column(
        Enum(LeagueScope), default=LeagueScope.ALL_ORGS, nullable=False
    )
    org_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # → hockey_blast.organizations.id (no FK constraint — cross-DB)
    division_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # → hockey_blast.divisions.id
    season_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # → hockey_blast.seasons.id

    # ── Commissioner ───────────────────────────────────────────────────────────
    commissioner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # → pred_users.id (no FK constraint for simplicity; enforced in service layer)

    max_members: Mapped[int] = mapped_column(Integer, default=50, nullable=False)

    # ── Scoring config ─────────────────────────────────────────────────────────
    correct_pick_base_points: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    upset_bonus_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confidence_multiplier_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

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

    # ── Relationships ──────────────────────────────────────────────────────────
    members: Mapped[list["PredLeagueMember"]] = relationship(
        "PredLeagueMember", back_populates="league", lazy="dynamic"
    )
    standings: Mapped[list["PredLeagueStandings"]] = relationship(
        "PredLeagueStandings", back_populates="league", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<PredLeague id={self.id} name={self.name!r} code={self.join_code}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "season_label": self.season_label,
            "join_code": self.join_code,
            "is_active": self.is_active,
            "is_public": self.is_public,
            "scope": self.scope.value,
            "org_id": self.org_id,
            "division_id": self.division_id,
            "season_id": self.season_id,
            "commissioner_id": self.commissioner_id,
            "max_members": self.max_members,
            "correct_pick_base_points": self.correct_pick_base_points,
            "upset_bonus_enabled": self.upset_bonus_enabled,
            "confidence_multiplier_enabled": self.confidence_multiplier_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

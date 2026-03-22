"""
PredUser — a registered user of the predictions platform, authenticated via Auth0.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class PredUser(PredBase):
    """
    One PredUser per Auth0 subject (sub claim).
    Created/updated on every successful login via upsert in user_service.
    """

    __tablename__ = "pred_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    auth0_sub: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    # Format: "google-oauth2|1234567890"  or  "auth0|abc123"

    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Sourced from Auth0 `name` claim on first login; user can update.

    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # May be None if user denies email scope (Apple Sign In).

    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Sourced from Auth0 `picture` claim.

    given_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Sourced from Auth0 `given_name` claim (first name from identity provider).

    family_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Sourced from Auth0 `family_name` claim (last name from identity provider).

    # Linked hockey_blast human (optional — user connects their HB profile manually)
    hb_human_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # References hockey_blast.humans.id — no FK constraint (cross-DB)

    balance: Mapped[int] = mapped_column(Integer, default=1000, nullable=False, server_default="1000")
    # Virtual currency balance (paper money). Starts at 1000, modified by wagers on picks.

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    preferences_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.false(), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    league_memberships: Mapped[list["PredLeagueMember"]] = relationship(
        "PredLeagueMember", back_populates="user", lazy="dynamic"
    )
    picks: Mapped[list["PredPick"]] = relationship(
        "PredPick", back_populates="user", lazy="dynamic"
    )
    preferences: Mapped["PredUserPreferences | None"] = relationship(
        "PredUserPreferences", back_populates="user", uselist=False
    )
    captain_claims: Mapped[list["PredUserCaptainClaim"]] = relationship(
        "PredUserCaptainClaim", back_populates="user", lazy="dynamic"
    )
    notifications: Mapped[list["PredNotification"]] = relationship(
        "PredNotification", back_populates="user", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<PredUser id={self.id} name={self.display_name!r}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "given_name": self.given_name,
            "family_name": self.family_name,
            "email": self.email,
            "avatar_url": self.avatar_url,
            "hb_human_id": self.hb_human_id,
            "balance": self.balance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "preferences_completed": self.preferences_completed,
            "is_admin": self.is_admin,
        }

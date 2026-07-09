"""
FantasyTradeTurn — one manager's turn within a trade round.

Turns are ordered by `turn_order` (ascending fantasy points → lowest FP first).
`pass_number` distinguishes the first pass (1) from the second-chance round-robin
pass (2) offered to managers who missed their first turn.

A turn resolves in one of three ways:
  - completed (made a swap): released_hb_human_id + acquired_hb_human_id set, acted_at set
  - skipped (chose to keep team): is_skipped=True, acted_at set
  - missed (deadline passed): is_missed=True (eligible for a pass-2 second chance)

Exactly one swap per turn (release one, acquire one of the same type).
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class FantasyTradeTurn(PredBase):
    __tablename__ = "fantasy_trade_turns"
    __table_args__ = (
        UniqueConstraint(
            "round_id", "user_id", "pass_number",
            name="uq_fantasy_trade_turns_round_user_pass",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_id: Mapped[int] = mapped_column(
        Integer, sa.ForeignKey("fantasy_trade_rounds.id"), nullable=False
    )
    league_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, sa.ForeignKey("pred_users.id"), nullable=False
    )
    # Position within the round; pass 1 = FP order, pass 2 = second chance for missers.
    turn_order: Mapped[int] = mapped_column(Integer, nullable=False)
    pass_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Outcome
    released_hb_human_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acquired_hb_human_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_missed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    round: Mapped["FantasyTradeRound"] = relationship(
        "FantasyTradeRound", back_populates="turns"
    )

    @property
    def is_resolved(self) -> bool:
        """A turn is resolved once the manager acted, skipped, or missed it."""
        return bool(self.acted_at) or self.is_skipped or self.is_missed

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "round_id": self.round_id,
            "league_id": self.league_id,
            "user_id": self.user_id,
            "turn_order": self.turn_order,
            "pass_number": self.pass_number,
            "released_hb_human_id": self.released_hb_human_id,
            "acquired_hb_human_id": self.acquired_hb_human_id,
            "is_skipped": self.is_skipped,
            "is_missed": self.is_missed,
            "is_resolved": self.is_resolved,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "acted_at": self.acted_at.isoformat() if self.acted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<FantasyTradeTurn id={self.id} round={self.round_id} "
            f"user={self.user_id} pass={self.pass_number} order={self.turn_order}>"
        )


from app.models.fantasy_trade_round import FantasyTradeRound  # noqa: E402

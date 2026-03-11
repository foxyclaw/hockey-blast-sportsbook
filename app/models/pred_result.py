"""
PredResult — the graded outcome of a PredPick.
Created by the background grader job after a game reaches a final status.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import PredBase


class PredResult(PredBase):
    """
    Graded result for a single PredPick. Created once per pick after game resolution.

    Points formula (if correct):
        base = league.correct_pick_base_points  (default 10)
        upset_bonus = max(0, floor(skill_differential × UPSET_SCALE))  [if enabled]
        pre_multiplier = base + upset_bonus
        total_points = pre_multiplier × confidence

    If wrong, forfeited, or canceled: total_points = 0.
    """

    __tablename__ = "pred_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    pick_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pred_picks.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    # ── Actual game outcome ───────────────────────────────────────────────────
    actual_winner_team_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Null for forfeits / canceled games.

    game_final_status: Mapped[str] = mapped_column(String(32), nullable=False)
    # "Final", "Final/OT", "Final/SO", "Forfeit", "CANCELED"

    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True if picked_team_id == actual_winner_team_id

    # ── Points breakdown ──────────────────────────────────────────────────────
    base_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    upset_bonus_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pre_multiplier_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # = base_points + upset_bonus_points

    confidence_multiplier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Copied from pick.confidence at grading time.

    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # = pre_multiplier_points × confidence_multiplier

    graded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    pick: Mapped["PredPick"] = relationship("PredPick", back_populates="result")

    def __repr__(self) -> str:
        return (
            f"<PredResult id={self.id} pick={self.pick_id} "
            f"correct={self.is_correct} pts={self.total_points}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pick_id": self.pick_id,
            "actual_winner_team_id": self.actual_winner_team_id,
            "game_final_status": self.game_final_status,
            "is_correct": self.is_correct,
            "base_points": self.base_points,
            "upset_bonus_points": self.upset_bonus_points,
            "pre_multiplier_points": self.pre_multiplier_points,
            "confidence_multiplier": self.confidence_multiplier,
            "total_points": self.total_points,
            "graded_at": self.graded_at.isoformat() if self.graded_at else None,
        }

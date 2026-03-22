"""
GamePredictionLog — snapshot of the system's predicted winner at pick-lock time.

One row per HB game. Created automatically when the first pick for a game is submitted.

Cross-DB references (no FK constraints — data lives in hockey_blast DB):
    game_id               → hockey_blast.games.id
    org_id                → hockey_blast.organizations.id
    home_team_id          → hockey_blast.teams.id
    away_team_id          → hockey_blast.teams.id
    predicted_winner_team_id → hockey_blast.teams.id

Key rule: lower avg_skill = better team (0=elite, 100=worst).
Predicted winner = team with lower avg_skill.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import PredBase


class GamePredictionLog(PredBase):
    """
    Snapshot of the system's predicted game winner, taken at first-pick time.

    skill_differential = away_avg_skill - home_avg_skill
    predicted_winner_team_id = team with lower avg_skill (None if either skill is unknown)
    """

    __tablename__ = "game_prediction_logs"
    __table_args__ = (
        UniqueConstraint("game_id", name="uq_game_prediction_log_game_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # HB game reference
    game_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    org_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Game info at snapshot time
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    game_scheduled_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Teams
    home_team_id: Mapped[int] = mapped_column(Integer, nullable=False)
    away_team_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Skill values at snapshot time
    home_avg_skill: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    away_avg_skill: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    # away_avg_skill - home_avg_skill (positive = away team is worse / home favored)
    skill_differential: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    # Team with lower avg_skill (the predicted winner); None if skills unknown
    predicted_winner_team_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # When this snapshot was taken
    snapshotted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

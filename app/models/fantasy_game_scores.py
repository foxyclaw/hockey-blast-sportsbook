"""
FantasyGameScores — per-game fantasy scoring for a rostered player.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import PredBase


class FantasyGameScores(PredBase):
    __tablename__ = "fantasy_game_scores"
    __table_args__ = (
        UniqueConstraint("league_id", "hb_human_id", "game_id", name="uq_fantasy_game_scores_league_human_game"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    league_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("fantasy_leagues.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("pred_users.id"), nullable=False)
    hb_human_id: Mapped[int] = mapped_column(Integer, nullable=False)
    game_id: Mapped[int] = mapped_column(Integer, nullable=False)
    goals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    penalties: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    games_played: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_goalie_win: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_shutout: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ref_games: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ref_penalties: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ref_gm: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False, default=0)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "league_id": self.league_id,
            "user_id": self.user_id,
            "hb_human_id": self.hb_human_id,
            "game_id": self.game_id,
            "goals": self.goals,
            "assists": self.assists,
            "penalties": self.penalties,
            "games_played": self.games_played,
            "is_goalie_win": self.is_goalie_win,
            "is_shutout": self.is_shutout,
            "ref_games": self.ref_games,
            "ref_penalties": self.ref_penalties,
            "ref_gm": self.ref_gm,
            "points": float(self.points),
            "scored_at": self.scored_at.isoformat() if self.scored_at else None,
        }

    def __repr__(self) -> str:
        return f"<FantasyGameScores id={self.id} league_id={self.league_id} game_id={self.game_id}>"

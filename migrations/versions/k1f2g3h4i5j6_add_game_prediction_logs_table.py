"""add game_prediction_logs table

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2026-03-21 23:00:00.000000

"""
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k1f2g3h4i5j6"
down_revision: str = "j0e1f2g3h4i5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_prediction_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("game_scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("home_avg_skill", sa.Numeric(6, 2), nullable=True),
        sa.Column("away_avg_skill", sa.Numeric(6, 2), nullable=True),
        sa.Column("skill_differential", sa.Numeric(6, 2), nullable=True),
        sa.Column("predicted_winner_team_id", sa.Integer(), nullable=True),
        sa.Column("snapshotted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", name="uq_game_prediction_log_game_id"),
    )
    op.create_index("ix_game_prediction_logs_game_id", "game_prediction_logs", ["game_id"])
    op.create_index("ix_game_prediction_logs_org_id", "game_prediction_logs", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_game_prediction_logs_org_id", table_name="game_prediction_logs")
    op.drop_index("ix_game_prediction_logs_game_id", table_name="game_prediction_logs")
    op.drop_table("game_prediction_logs")

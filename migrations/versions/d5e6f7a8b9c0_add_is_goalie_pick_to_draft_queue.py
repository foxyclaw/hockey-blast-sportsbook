"""add is_goalie_pick to fantasy_draft_queue

Revision ID: d5e6f7a8b9c0
Revises: 7d27468b9a94
Create Date: 2026-03-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision: str = "d5e6f7a8b9c0"
down_revision: str = "7d27468b9a94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fantasy_draft_queue",
        sa.Column("is_goalie_pick", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("fantasy_draft_queue", "is_goalie_pick")

"""add season_label to pred_leagues

Revision ID: a1b2c3d4e5f6
Revises: 5e95446b0372
Create Date: 2026-03-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "5e95446b0372"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pred_leagues",
        sa.Column("season_label", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pred_leagues", "season_label")

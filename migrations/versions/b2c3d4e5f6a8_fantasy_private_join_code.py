"""fantasy_private_join_code

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-03-18

Add is_private and join_code columns to fantasy_leagues.
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fantasy_leagues",
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "fantasy_leagues",
        sa.Column("join_code", sa.String(12), nullable=True),
    )


def downgrade():
    op.drop_column("fantasy_leagues", "join_code")
    op.drop_column("fantasy_leagues", "is_private")

"""add is_provisional to fantasy_game_scores

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'u1v2w3x4y5z6'
down_revision = 't0u1v2w3x4y5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'fantasy_game_scores',
        sa.Column('is_provisional', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade():
    op.drop_column('fantasy_game_scores', 'is_provisional')

"""add is_goalie_tie to fantasy_game_scores

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = 'y5z6a7b8c9d0'
down_revision = 'x4y5z6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'fantasy_game_scores',
        sa.Column('is_goalie_tie', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade():
    op.drop_column('fantasy_game_scores', 'is_goalie_tie')

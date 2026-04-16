"""add min_games_played to fantasy_leagues

Revision ID: f1a2b3c4d5e6
Revises: e91cae0261cb
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = 'e91cae0261cb'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'fantasy_leagues',
        sa.Column('min_games_played', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade():
    op.drop_column('fantasy_leagues', 'min_games_played')

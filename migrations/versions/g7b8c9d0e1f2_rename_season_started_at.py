"""rename season_started_at to season_starts_at

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-19
"""
from alembic import op

revision = 'g7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('fantasy_leagues', 'season_started_at', new_column_name='season_starts_at')


def downgrade():
    op.alter_column('fantasy_leagues', 'season_starts_at', new_column_name='season_started_at')

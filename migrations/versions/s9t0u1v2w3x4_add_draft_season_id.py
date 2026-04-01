"""add draft_season_id to fantasy_leagues

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = 's9t0u1v2w3x4'
down_revision = 'r8s9t0u1v2w3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('fantasy_leagues', sa.Column('draft_season_id', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('fantasy_leagues', 'draft_season_id')

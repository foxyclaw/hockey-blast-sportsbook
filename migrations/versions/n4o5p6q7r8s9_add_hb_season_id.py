"""add hb_season_id to fantasy_leagues

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'n4o5p6q7r8s9'
down_revision = 'm3n4o5p6q7r8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('fantasy_leagues', sa.Column('hb_season_id', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('fantasy_leagues', 'hb_season_id')

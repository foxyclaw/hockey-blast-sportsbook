"""add hb_league_id to fantasy_leagues

Revision ID: m3n4o5p6q7r8
Revises: l2g3h4i5j6k7
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'm3n4o5p6q7r8'
down_revision = 'l2g3h4i5j6k7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('fantasy_leagues', sa.Column('hb_league_id', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('fantasy_leagues', 'hb_league_id')

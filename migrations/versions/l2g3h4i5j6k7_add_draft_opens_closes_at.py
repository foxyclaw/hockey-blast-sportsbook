"""add draft_opens_at and draft_closes_at to fantasy_leagues

Revision ID: l2g3h4i5j6k7
Revises: k1f2g3h4i5j6
Create Date: 2026-03-22
"""
from alembic import op
import sqlalchemy as sa

revision = 'l2g3h4i5j6k7'
down_revision = 'k1f2g3h4i5j6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('fantasy_leagues', sa.Column('draft_opens_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('fantasy_leagues', sa.Column('draft_closes_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('fantasy_leagues', 'draft_closes_at')
    op.drop_column('fantasy_leagues', 'draft_opens_at')

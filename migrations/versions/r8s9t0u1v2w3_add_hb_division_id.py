"""add hb_division_id to fantasy_leagues

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-03-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'r8s9t0u1v2w3'
down_revision = 'q7r8s9t0u1v2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('fantasy_leagues', sa.Column('hb_division_id', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('fantasy_leagues', 'hb_division_id')

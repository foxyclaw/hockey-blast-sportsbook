"""add max_pool_skaters to fantasy_leagues

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'x4y5z6a7b8c9'
down_revision = 'w3x4y5z6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'fantasy_leagues',
        sa.Column('max_pool_skaters', sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column('fantasy_leagues', 'max_pool_skaters')

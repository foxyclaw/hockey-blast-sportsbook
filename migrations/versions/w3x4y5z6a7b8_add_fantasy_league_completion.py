"""add completed_at + winner_user_id to fantasy_leagues

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'w3x4y5z6a7b8'
down_revision = 'v2w3x4y5z6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'fantasy_leagues',
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'fantasy_leagues',
        sa.Column('winner_user_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_fantasy_leagues_winner_user_id',
        'fantasy_leagues', 'pred_users',
        ['winner_user_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint('fk_fantasy_leagues_winner_user_id', 'fantasy_leagues', type_='foreignkey')
    op.drop_column('fantasy_leagues', 'winner_user_id')
    op.drop_column('fantasy_leagues', 'completed_at')

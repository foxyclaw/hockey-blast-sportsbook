"""add fantasy_manager_queue table

Revision ID: e91cae0261cb
Revises: s9t0u1v2w3x4
Create Date: 2026-04-02 23:33:13.782599+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e91cae0261cb'
down_revision: Union[str, None] = 's9t0u1v2w3x4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fantasy_manager_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('league_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('hb_human_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['league_id'], ['fantasy_leagues.id']),
        sa.ForeignKeyConstraint(['user_id'], ['pred_users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('league_id', 'user_id', 'hb_human_id', name='uq_fmq_league_user_human'),
    )
    op.create_index('ix_fantasy_manager_queue_league_id', 'fantasy_manager_queue', ['league_id'])


def downgrade() -> None:
    op.drop_index('ix_fantasy_manager_queue_league_id', table_name='fantasy_manager_queue')
    op.drop_table('fantasy_manager_queue')

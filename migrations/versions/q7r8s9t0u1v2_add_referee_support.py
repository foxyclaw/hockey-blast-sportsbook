"""add referee support to fantasy

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

revision = 'q7r8s9t0u1v2'
down_revision = 'p6q7r8s9t0u1'
branch_labels = None
depends_on = None


def upgrade():
    # fantasy_leagues: add roster_refs column (default 0 = backward compat)
    op.add_column('fantasy_leagues', sa.Column('roster_refs', sa.Integer(), nullable=False, server_default='0'))

    # fantasy_roster: add is_ref column
    op.add_column('fantasy_roster', sa.Column('is_ref', sa.Boolean(), nullable=False, server_default='false'))

    # fantasy_draft_queue: add is_ref_pick column
    op.add_column('fantasy_draft_queue', sa.Column('is_ref_pick', sa.Boolean(), nullable=False, server_default='false'))

    # fantasy_game_scores: add ref scoring columns
    op.add_column('fantasy_game_scores', sa.Column('ref_games', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('fantasy_game_scores', sa.Column('ref_penalties', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('fantasy_game_scores', sa.Column('ref_gm', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('fantasy_game_scores', 'ref_gm')
    op.drop_column('fantasy_game_scores', 'ref_penalties')
    op.drop_column('fantasy_game_scores', 'ref_games')
    op.drop_column('fantasy_draft_queue', 'is_ref_pick')
    op.drop_column('fantasy_roster', 'is_ref')
    op.drop_column('fantasy_leagues', 'roster_refs')

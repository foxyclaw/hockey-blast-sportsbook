"""add fantasy_trade_rounds and fantasy_trade_turns

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'v2w3x4y5z6a7'
down_revision = 'u1v2w3x4y5z6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fantasy_trade_rounds',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('league_id', sa.Integer(), sa.ForeignKey('fantasy_leagues.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('pick_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('pred_users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_fantasy_trade_rounds_league', 'fantasy_trade_rounds', ['league_id'])

    op.create_table(
        'fantasy_trade_turns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('round_id', sa.Integer(), sa.ForeignKey('fantasy_trade_rounds.id'), nullable=False),
        sa.Column('league_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('pred_users.id'), nullable=False),
        sa.Column('turn_order', sa.Integer(), nullable=False),
        sa.Column('pass_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('released_hb_human_id', sa.Integer(), nullable=True),
        sa.Column('acquired_hb_human_id', sa.Integer(), nullable=True),
        sa.Column('is_skipped', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_missed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('round_id', 'user_id', 'pass_number',
                            name='uq_fantasy_trade_turns_round_user_pass'),
    )
    op.create_index('ix_fantasy_trade_turns_round', 'fantasy_trade_turns', ['round_id'])


def downgrade():
    op.drop_index('ix_fantasy_trade_turns_round', table_name='fantasy_trade_turns')
    op.drop_table('fantasy_trade_turns')
    op.drop_index('ix_fantasy_trade_rounds_league', table_name='fantasy_trade_rounds')
    op.drop_table('fantasy_trade_rounds')

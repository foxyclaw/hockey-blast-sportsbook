"""add site_events table

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'h8c9d0e1f2g3'
down_revision = 'g7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'site_events',
        sa.Column('id',         sa.Integer(),     nullable=False),
        sa.Column('event_type', sa.String(32),    nullable=False),
        sa.Column('user_id',    sa.Integer(),     nullable=True),
        sa.Column('ip_address', sa.String(45),    nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_site_events_event_type', 'site_events', ['event_type'])
    op.create_index('ix_site_events_user_id',    'site_events', ['user_id'])
    op.create_index('ix_site_events_ip_address', 'site_events', ['ip_address'])
    op.create_index('ix_site_events_created_at', 'site_events', ['created_at'])


def downgrade():
    op.drop_table('site_events')

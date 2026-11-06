"""add migrated_at + migrated_to_url to fantasy_leagues

Set by the social site's import (hbs-fantasy FANTASY_DESIGN.md §6.3) once a
league has been copied to hockey-blast.com. A migrated league is read-only here:
every fantasy write returns 409 and the fantasy jobs skip it.

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'z6a7b8c9d0e1'
down_revision = 'y5z6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'fantasy_leagues',
        sa.Column('migrated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'fantasy_leagues',
        sa.Column('migrated_to_url', sa.String(length=256), nullable=True),
    )


def downgrade():
    op.drop_column('fantasy_leagues', 'migrated_to_url')
    op.drop_column('fantasy_leagues', 'migrated_at')

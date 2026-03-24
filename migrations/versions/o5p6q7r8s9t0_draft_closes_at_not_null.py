"""make draft_closes_at NOT NULL

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-03-24

"""
from alembic import op
import sqlalchemy as sa

revision = 'o5p6q7r8s9t0'
down_revision = 'n4o5p6q7r8s9'
branch_labels = None
depends_on = None


def upgrade():
    # Set a sensible default for any existing NULLs before enforcing NOT NULL
    op.execute("""
        UPDATE fantasy_leagues
        SET draft_closes_at = created_at + INTERVAL '2 hours'
        WHERE draft_closes_at IS NULL
    """)
    op.alter_column('fantasy_leagues', 'draft_closes_at',
                    existing_type=sa.DateTime(timezone=True),
                    nullable=False)


def downgrade():
    op.alter_column('fantasy_leagues', 'draft_closes_at',
                    existing_type=sa.DateTime(timezone=True),
                    nullable=True)

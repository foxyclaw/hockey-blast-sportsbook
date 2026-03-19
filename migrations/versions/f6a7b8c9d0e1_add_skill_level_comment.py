"""add skill_level_comment to pred_user_preferences

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pred_user_preferences",
        sa.Column("skill_level_comment", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pred_user_preferences", "skill_level_comment")

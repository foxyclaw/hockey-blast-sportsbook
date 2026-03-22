"""add given_name and family_name to pred_users

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-03-21 17:00:00.000000

"""
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j0e1f2g3h4i5"
down_revision: str = "i9d0e1f2g3h4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pred_users", sa.Column("given_name", sa.String(64), nullable=True))
    op.add_column("pred_users", sa.Column("family_name", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("pred_users", "family_name")
    op.drop_column("pred_users", "given_name")

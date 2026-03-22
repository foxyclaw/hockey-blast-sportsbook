"""add merged_at to pred_user_hb_claims

Revision ID: i9d0e1f2g3h4
Revises: 24af90c12f88, h8c9d0e1f2g3
Create Date: 2026-03-21

Adds merged_at (TIMESTAMP WITH TIME ZONE, nullable) to pred_user_hb_claims.
This column is stamped when the secondary human has been merged into the primary
on the hockey_blast side via merge_humans().
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i9d0e1f2g3h4"
down_revision: Union[str, None] = ("24af90c12f88", "h8c9d0e1f2g3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pred_user_hb_claims",
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pred_user_hb_claims", "merged_at")

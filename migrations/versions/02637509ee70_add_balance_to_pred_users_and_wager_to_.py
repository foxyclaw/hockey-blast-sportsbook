"""add balance to pred_users and wager to pred_picks and pred_results

Revision ID: 02637509ee70
Revises: 0001
Create Date: 2026-03-11 16:42:16.021110+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "02637509ee70"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Feature 1: Paper Money — add balance to pred_users
    op.add_column(
        "pred_users",
        sa.Column(
            "balance",
            sa.Integer(),
            server_default="1000",
            nullable=False,
        ),
    )

    # Add wager column to pred_picks
    op.add_column(
        "pred_picks",
        sa.Column("wager", sa.Integer(), nullable=True),
    )

    # Add wager + balance_change columns to pred_results
    op.add_column(
        "pred_results",
        sa.Column("wager", sa.Integer(), nullable=True),
    )
    op.add_column(
        "pred_results",
        sa.Column("balance_change", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pred_results", "balance_change")
    op.drop_column("pred_results", "wager")
    op.drop_column("pred_picks", "wager")
    op.drop_column("pred_users", "balance")

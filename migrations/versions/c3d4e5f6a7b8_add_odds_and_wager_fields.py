"""add odds and wager fields

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── pred_picks: add odds/wager snapshot fields ─────────────────────────────
    op.add_column(
        "pred_picks",
        sa.Column("odds_at_pick", sa.Numeric(6, 2), nullable=True),
    )
    op.add_column(
        "pred_picks",
        sa.Column("effective_wager", sa.Integer(), nullable=True),
    )
    op.add_column(
        "pred_picks",
        sa.Column("potential_payout", sa.Integer(), nullable=True),
    )

    # ── pred_results: add payout and balance_delta fields ─────────────────────
    op.add_column(
        "pred_results",
        sa.Column("payout", sa.Integer(), nullable=True),
    )
    op.add_column(
        "pred_results",
        sa.Column("balance_delta", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pred_results", "balance_delta")
    op.drop_column("pred_results", "payout")
    op.drop_column("pred_picks", "potential_payout")
    op.drop_column("pred_picks", "effective_wager")
    op.drop_column("pred_picks", "odds_at_pick")

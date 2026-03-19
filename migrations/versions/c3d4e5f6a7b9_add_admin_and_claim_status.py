"""add is_admin to pred_users and claim_status fields to pred_user_hb_claims

Revision ID: c3d4e5f6a7b9
Revises: f6a7b8c9d0e1
Create Date: 2026-03-18 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b9"
down_revision = ("b2c3d4e5f6a8", "f6a7b8c9d0e1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pred_users: add is_admin column
    op.add_column(
        "pred_users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # pred_user_hb_claims: add claim lifecycle fields
    op.add_column(
        "pred_user_hb_claims",
        sa.Column(
            "claim_status",
            sa.String(20),
            nullable=False,
            server_default="confirmed",
        ),
    )
    op.add_column(
        "pred_user_hb_claims",
        sa.Column("admin_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "pred_user_hb_claims",
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("pred_users.id"), nullable=True),
    )
    op.add_column(
        "pred_user_hb_claims",
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("pred_user_hb_claims", "reviewed_at")
    op.drop_column("pred_user_hb_claims", "reviewed_by")
    op.drop_column("pred_user_hb_claims", "admin_note")
    op.drop_column("pred_user_hb_claims", "claim_status")
    op.drop_column("pred_users", "is_admin")

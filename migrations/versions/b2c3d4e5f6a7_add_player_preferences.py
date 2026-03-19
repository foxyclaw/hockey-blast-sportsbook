"""add player preferences

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── pred_user_preferences ──────────────────────────────────────────────────
    op.create_table(
        "pred_user_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("skill_level", sa.String(20), nullable=True),
        sa.Column("is_free_agent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("wants_to_sub", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notify_email", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_phone", sa.String(20), nullable=True),
        sa.Column("interested_location_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["pred_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_pred_user_preferences_user_id"),
        "pred_user_preferences",
        ["user_id"],
        unique=True,
    )

    # ── pred_user_captain_claims ───────────────────────────────────────────────
    op.create_table(
        "pred_user_captain_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("team_name", sa.String(128), nullable=False),
        sa.Column("org_name", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["pred_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "team_id", name="uq_captain_user_team"),
    )
    op.create_index(
        op.f("ix_pred_user_captain_claims_user_id"),
        "pred_user_captain_claims",
        ["user_id"],
        unique=False,
    )

    # ── preferences_completed column on pred_users ─────────────────────────────
    op.add_column(
        "pred_users",
        sa.Column(
            "preferences_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("pred_users", "preferences_completed")
    op.drop_index(
        op.f("ix_pred_user_captain_claims_user_id"),
        table_name="pred_user_captain_claims",
    )
    op.drop_table("pred_user_captain_claims")
    op.drop_index(
        op.f("ix_pred_user_preferences_user_id"),
        table_name="pred_user_preferences",
    )
    op.drop_table("pred_user_preferences")

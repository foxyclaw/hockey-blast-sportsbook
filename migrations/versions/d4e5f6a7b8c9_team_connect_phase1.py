"""team connect phase 1 - notifications, sub requests, roster invites

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── pred_notifications ─────────────────────────────────────────────────────
    op.create_table(
        "pred_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.String(500), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["pred_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pred_notifications_user_id", "pred_notifications", ["user_id"])

    # ── pred_sub_requests ──────────────────────────────────────────────────────
    op.create_table(
        "pred_sub_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("hb_team_id", sa.Integer(), nullable=False),
        sa.Column("captain_user_id", sa.Integer(), nullable=False),
        sa.Column("goalies_needed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skaters_needed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["captain_user_id"], ["pred_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── pred_sub_responses ─────────────────────────────────────────────────────
    op.create_table(
        "pred_sub_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="interested"),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["request_id"], ["pred_sub_requests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["pred_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", "user_id", name="uq_sub_response"),
    )

    # ── pred_roster_invites ────────────────────────────────────────────────────
    op.create_table(
        "pred_roster_invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=False),
        sa.Column("to_user_id", sa.Integer(), nullable=False),
        sa.Column("hb_team_id", sa.Integer(), nullable=False),
        sa.Column("team_name", sa.String(128), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["from_user_id"], ["pred_users.id"]),
        sa.ForeignKeyConstraint(["to_user_id"], ["pred_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_user_id", "to_user_id", "hb_team_id", name="uq_roster_invite"),
    )

    # ── pred_team_stubs ────────────────────────────────────────────────────────
    op.create_table(
        "pred_team_stubs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creator_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("level_preference", sa.String(20), nullable=True),
        sa.Column("location_ids", sa.JSON(), nullable=True, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="recruiting"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["creator_user_id"], ["pred_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("pred_team_stubs")
    op.drop_table("pred_roster_invites")
    op.drop_table("pred_sub_responses")
    op.drop_table("pred_sub_requests")
    op.drop_index("ix_pred_notifications_user_id", "pred_notifications")
    op.drop_table("pred_notifications")

"""Initial migration — create all pred_ tables

Revision ID: 0001
Revises:
Create Date: 2026-03-11 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── pred_users ─────────────────────────────────────────────────────────────
    op.create_table(
        "pred_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("auth0_sub", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("email", sa.String(256), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("hb_human_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pred_users")),
        sa.UniqueConstraint("auth0_sub", name=op.f("uq_pred_users_auth0_sub")),
    )
    op.create_index(op.f("ix_pred_users_auth0_sub"), "pred_users", ["auth0_sub"], unique=True)
    op.create_index(op.f("ix_pred_users_hb_human_id"), "pred_users", ["hb_human_id"], unique=False)

    # ── pred_leagues ───────────────────────────────────────────────────────────
    op.create_table(
        "pred_leagues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("join_code", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "scope",
            sa.Enum(
                "ALL_ORGS", "ORG", "DIVISION", "CUSTOM",
                name="leaguescope",
            ),
            nullable=False,
            server_default="ALL_ORGS",
        ),
        sa.Column("org_id", sa.Integer(), nullable=True),
        sa.Column("division_id", sa.Integer(), nullable=True),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("commissioner_id", sa.Integer(), nullable=False),
        sa.Column("max_members", sa.Integer(), nullable=False, server_default="50"),
        sa.Column(
            "correct_pick_base_points", sa.Integer(), nullable=False, server_default="10"
        ),
        sa.Column(
            "upset_bonus_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "confidence_multiplier_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pred_leagues")),
        sa.UniqueConstraint("join_code", name=op.f("uq_pred_leagues_join_code")),
    )

    # ── pred_league_members ────────────────────────────────────────────────────
    op.create_table(
        "pred_league_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("COMMISSIONER", "MEMBER", name="memberrole"),
            nullable=False,
            server_default="MEMBER",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["pred_users.id"], name=op.f("fk_pred_league_members_user_id_pred_users")
        ),
        sa.ForeignKeyConstraint(
            ["league_id"],
            ["pred_leagues.id"],
            name=op.f("fk_pred_league_members_league_id_pred_leagues"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pred_league_members")),
        sa.UniqueConstraint("user_id", "league_id", name="uq_user_league"),
    )
    op.create_index(
        op.f("ix_pred_league_members_user_id"), "pred_league_members", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_pred_league_members_league_id"),
        "pred_league_members",
        ["league_id"],
        unique=False,
    )

    # ── pred_picks ─────────────────────────────────────────────────────────────
    op.create_table(
        "pred_picks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("game_scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("picked_team_id", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("home_team_avg_skill", sa.Numeric(6, 2), nullable=True),
        sa.Column("away_team_avg_skill", sa.Numeric(6, 2), nullable=True),
        sa.Column("picked_team_avg_skill", sa.Numeric(6, 2), nullable=True),
        sa.Column("opponent_avg_skill", sa.Numeric(6, 2), nullable=True),
        sa.Column("skill_differential", sa.Numeric(6, 2), nullable=True),
        sa.Column("is_upset_pick", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("confidence IN (1, 2, 3)", name="ck_confidence_valid"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["pred_users.id"], name=op.f("fk_pred_picks_user_id_pred_users")
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["pred_leagues.id"], name=op.f("fk_pred_picks_league_id_pred_leagues")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pred_picks")),
        sa.UniqueConstraint(
            "user_id", "game_id", "league_id", name="uq_pick_user_game_league"
        ),
    )
    op.create_index(op.f("ix_pred_picks_user_id"), "pred_picks", ["user_id"], unique=False)
    op.create_index(op.f("ix_pred_picks_league_id"), "pred_picks", ["league_id"], unique=False)
    op.create_index(op.f("ix_pred_picks_game_id"), "pred_picks", ["game_id"], unique=False)

    # ── pred_results ───────────────────────────────────────────────────────────
    op.create_table(
        "pred_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pick_id", sa.Integer(), nullable=False),
        sa.Column("actual_winner_team_id", sa.Integer(), nullable=True),
        sa.Column("game_final_status", sa.String(32), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("base_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upset_bonus_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pre_multiplier_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_multiplier", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "graded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["pick_id"], ["pred_picks.id"], name=op.f("fk_pred_results_pick_id_pred_picks")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pred_results")),
        sa.UniqueConstraint("pick_id", name=op.f("uq_pred_results_pick_id")),
    )
    op.create_index(op.f("ix_pred_results_pick_id"), "pred_results", ["pick_id"], unique=True)

    # ── pred_league_standings ──────────────────────────────────────────────────
    op.create_table(
        "pred_league_standings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("total_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_picks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_picks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("upset_picks_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high_conf_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pick_accuracy", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["pred_users.id"],
            name=op.f("fk_pred_league_standings_user_id_pred_users"),
        ),
        sa.ForeignKeyConstraint(
            ["league_id"],
            ["pred_leagues.id"],
            name=op.f("fk_pred_league_standings_league_id_pred_leagues"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pred_league_standings")),
        sa.UniqueConstraint("user_id", "league_id", name="uq_standings_user_league"),
    )
    op.create_index(
        op.f("ix_pred_league_standings_user_id"),
        "pred_league_standings",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pred_league_standings_league_id"),
        "pred_league_standings",
        ["league_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("pred_league_standings")
    op.drop_table("pred_results")
    op.drop_table("pred_picks")
    op.drop_table("pred_league_members")
    op.drop_table("pred_leagues")
    op.drop_table("pred_users")

    # Drop enum types (PostgreSQL)
    op.execute("DROP TYPE IF EXISTS leaguescope")
    op.execute("DROP TYPE IF EXISTS memberrole")

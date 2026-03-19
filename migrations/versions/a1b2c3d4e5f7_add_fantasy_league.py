"""add fantasy league tables

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-03-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: str = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fantasy_leagues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("level_id", sa.Integer(), nullable=False),
        sa.Column("level_name", sa.String(64), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("season_label", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="forming"),
        sa.Column("max_managers", sa.Integer(), nullable=False),
        sa.Column("roster_skaters", sa.Integer(), nullable=False),
        sa.Column("roster_goalies", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("draft_pick_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("pred_users.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("draft_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("season_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "fantasy_managers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("fantasy_leagues.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("pred_users.id"), nullable=False),
        sa.Column("team_name", sa.String(64), nullable=False),
        sa.Column("draft_position", sa.Integer(), nullable=True),
        sa.Column("compensatory_picks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("league_id", "user_id", name="uq_fantasy_managers_league_user"),
    )

    op.create_table(
        "fantasy_roster",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("fantasy_leagues.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("pred_users.id"), nullable=False),
        sa.Column("hb_human_id", sa.Integer(), nullable=False),
        sa.Column("is_goalie", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("round_picked", sa.Integer(), nullable=True),
        sa.Column("pick_number", sa.Integer(), nullable=True),
        sa.Column("drafted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("league_id", "hb_human_id", name="uq_fantasy_roster_league_human"),
    )

    op.create_table(
        "fantasy_draft_queue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("fantasy_leagues.id"), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("pick_in_round", sa.Integer(), nullable=False),
        sa.Column("overall_pick", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("pred_users.id"), nullable=False),
        sa.Column("hb_human_id", sa.Integer(), nullable=True),
        sa.Column("is_skipped", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deadline", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("picked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("league_id", "overall_pick", name="uq_fantasy_draft_queue_league_pick"),
    )

    op.create_table(
        "fantasy_game_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("fantasy_leagues.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("pred_users.id"), nullable=False),
        sa.Column("hb_human_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assists", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("penalties", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("games_played", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_goalie_win", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_shutout", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("points", sa.Numeric(6, 1), nullable=False, server_default="0"),
        sa.Column("scored_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("league_id", "hb_human_id", "game_id", name="uq_fantasy_game_scores_league_human_game"),
    )

    op.create_table(
        "fantasy_standings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("fantasy_leagues.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("pred_users.id"), nullable=False),
        sa.Column("total_points", sa.Numeric(8, 1), nullable=False, server_default="0"),
        sa.Column("week_points", sa.Numeric(8, 1), nullable=False, server_default="0"),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("league_id", "user_id", name="uq_fantasy_standings_league_user"),
    )


def downgrade() -> None:
    op.drop_table("fantasy_standings")
    op.drop_table("fantasy_game_scores")
    op.drop_table("fantasy_draft_queue")
    op.drop_table("fantasy_roster")
    op.drop_table("fantasy_managers")
    op.drop_table("fantasy_leagues")

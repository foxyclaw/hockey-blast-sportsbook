"""add fee fields to sub_requests, roster_invites, team_stubs

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-18 02:20:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sub fee (per game, cents, can be 0)
    op.add_column("pred_sub_requests", sa.Column("sub_fee", sa.Integer(), nullable=False, server_default="0"))

    # Roster fees (full and half season, cents)
    op.add_column("pred_roster_invites", sa.Column("roster_fee_full", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pred_roster_invites", sa.Column("roster_fee_half", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("pred_team_stubs", sa.Column("roster_fee_full", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pred_team_stubs", sa.Column("roster_fee_half", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("pred_sub_requests", "sub_fee")
    op.drop_column("pred_roster_invites", "roster_fee_full")
    op.drop_column("pred_roster_invites", "roster_fee_half")
    op.drop_column("pred_team_stubs", "roster_fee_full")
    op.drop_column("pred_team_stubs", "roster_fee_half")

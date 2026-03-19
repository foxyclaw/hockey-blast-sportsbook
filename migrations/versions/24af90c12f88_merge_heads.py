"""merge heads

Revision ID: 24af90c12f88
Revises: e6f7a8b9c0d1, g7b8c9d0e1f2
Create Date: 2026-03-19 21:36:14.308438+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "24af90c12f88"
down_revision: Union[str, None] = ("e6f7a8b9c0d1", "g7b8c9d0e1f2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

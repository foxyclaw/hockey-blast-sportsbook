"""merge_heads

Revision ID: 7d27468b9a94
Revises: b2c3d4e5f6a8, c3d4e5f6a7b9
Create Date: 2026-03-18 20:17:30.560655+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7d27468b9a94"
down_revision: Union[str, None] = ("b2c3d4e5f6a8", "c3d4e5f6a7b9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

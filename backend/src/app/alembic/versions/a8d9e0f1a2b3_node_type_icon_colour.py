"""An optional icon and colour on each item type.

Revision ID: a8d9e0f1a2b3
Revises: z7c8d9e0f1a2
Create Date: 2026-10-29 21:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8d9e0f1a2b3"
down_revision: str | None = "z7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("node_types", sa.Column("icon", sa.String(), nullable=True))
    op.add_column("node_types", sa.Column("colour", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("node_types", "colour")
    op.drop_column("node_types", "icon")

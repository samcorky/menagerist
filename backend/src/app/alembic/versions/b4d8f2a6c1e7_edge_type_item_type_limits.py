"""edge_type_item_type_limits

Which item types a connection type may join at each end. An empty list means
no limit, so every existing connection type behaves as before.

Revision ID: b4d8f2a6c1e7
Revises: e3a7c1f9b5d2
Create Date: 2026-11-25 08:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4d8f2a6c1e7"
down_revision: str | None = "e3a7c1f9b5d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("source_types", "target_types"):
        op.add_column(
            "edge_types",
            sa.Column(
                column,
                postgresql.ARRAY(sa.String()),
                nullable=False,
                server_default="{}",
            ),
        )


def downgrade() -> None:
    op.drop_column("edge_types", "target_types")
    op.drop_column("edge_types", "source_types")

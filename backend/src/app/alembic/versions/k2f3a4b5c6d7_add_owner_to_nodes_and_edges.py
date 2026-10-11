"""add_owner_to_nodes_and_edges

Revision ID: k2f3a4b5c6d7
Revises: j1e2f3a4b5c6
Create Date: 2026-10-10 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k2f3a4b5c6d7"
down_revision: str | None = "j1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("nodes", "edges"):
        op.add_column(table, sa.Column("owner_id", sa.Uuid(), nullable=True))
        op.create_index(f"ix_{table}_owner_id_id", table, ["owner_id", "id"])


def downgrade() -> None:
    for table in ("edges", "nodes"):
        op.drop_index(f"ix_{table}_owner_id_id", table_name=table)
        op.drop_column(table, "owner_id")

"""partial_unique_type_slugs

A soft-deleted item type or relationship type no longer reserves its slug. The use
cases already check uniqueness among live rows, so the index only backs that check.

Downgrading rebuilds the full unique index, so it fails if a live and a soft-deleted
type now share a slug.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-06 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    ("node_types", "ix_node_types_slug", "uq_node_types_slug_live"),
    ("edge_types", "ix_edge_types_slug", "uq_edge_types_slug_live"),
)


def upgrade() -> None:
    for table, plain, live in _TABLES:
        op.drop_index(op.f(plain), table_name=table)
        op.create_index(op.f(plain), table, ["slug"], unique=False)
        op.create_index(
            live,
            table,
            ["slug"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    for table, plain, live in _TABLES:
        op.drop_index(
            live, table_name=table, postgresql_where=sa.text("deleted_at IS NULL")
        )
        op.drop_index(op.f(plain), table_name=table)
        op.create_index(op.f(plain), table, ["slug"], unique=True)

"""edge_reach_indexes

Partial composite indexes on live connections so following one relationship
through several hops looks up each step by (type, end) instead of scanning.

Revision ID: d5e1f3a8b2c9
Revises: c4d9e2a7f1b8
Create Date: 2026-11-15 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e1f3a8b2c9"
down_revision: str | None = "c4d9e2a7f1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_edges_live_type_source_id",
        "edges",
        ["type", "source_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_edges_live_type_target_id",
        "edges",
        ["type", "target_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_edges_live_type_target_id", table_name="edges")
    op.drop_index("ix_edges_live_type_source_id", table_name="edges")

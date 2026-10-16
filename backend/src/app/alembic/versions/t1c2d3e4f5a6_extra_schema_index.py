"""extra_schema_index

Revision ID: t1c2d3e4f5a6
Revises: s0b1c2d3e4f5
Create Date: 2026-10-16 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t1c2d3e4f5a6"
down_revision: str | None = "s0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Backs per-item field conditions in query_sql._declares.
    op.execute(
        """
        CREATE INDEX ix_nodes_extra_schema_gin ON nodes
        USING gin (extra_schema jsonb_path_ops)
        WHERE extra_schema IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_nodes_extra_schema_gin")

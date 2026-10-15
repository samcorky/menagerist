"""attributes_text_trgm

Revision ID: s0b1c2d3e4f5
Revises: r9a0b1c2d3e4
Create Date: 2026-10-15 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "s0b1c2d3e4f5"
down_revision: str | None = "r9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Backs the superset prefilter in search_sql.search_clause.
    op.execute(
        """
        CREATE INDEX ix_nodes_attributes_text_trgm ON nodes
        USING gin (immutable_unaccent((attributes)::text) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_nodes_attributes_text_trgm")

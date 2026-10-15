"""sort_indexes

Revision ID: r9a0b1c2d3e4
Revises: q8f9a0b1c2d3
Create Date: 2026-10-15 09:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r9a0b1c2d3e4"
down_revision: str | None = "q8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Match the sort expressions in query_sql.py, so ORDER BY can use them.
    # The ids stay ascending, so a descending name sort needs its own index: a
    # backward scan of the first would flip the id tie-break too. Timestamps
    # rarely tie, so descending reuses the ascending index (backward scan plus
    # an incremental sort of the ties).
    op.execute(
        """
        CREATE INDEX ix_nodes_owner_name_sort ON nodes
        (owner_id, (lower(immutable_unaccent(name)) COLLATE "C"), id)
        WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_owner_name_sort_desc ON nodes
        (owner_id, (lower(immutable_unaccent(name)) COLLATE "C") DESC, id)
        WHERE deleted_at IS NULL
        """
    )
    for column in ("created", "updated"):
        epoch = f"CAST(EXTRACT(epoch FROM timezone('UTC', {column}_at)) AS FLOAT)"
        op.execute(
            f"""
            CREATE INDEX ix_nodes_owner_{column}_sort ON nodes
            (owner_id, ({epoch}), id)
            WHERE deleted_at IS NULL
            """
        )


def downgrade() -> None:
    for column in ("updated", "created"):
        op.execute(f"DROP INDEX IF EXISTS ix_nodes_owner_{column}_sort")
    op.execute("DROP INDEX IF EXISTS ix_nodes_owner_name_sort_desc")
    op.execute("DROP INDEX IF EXISTS ix_nodes_owner_name_sort")

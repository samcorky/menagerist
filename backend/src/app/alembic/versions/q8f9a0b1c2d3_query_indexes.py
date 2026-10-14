"""query_indexes

Revision ID: q8f9a0b1c2d3
Revises: p7e8f9a0b1c2
Create Date: 2026-10-14 15:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q8f9a0b1c2d3"
down_revision: str | None = "p7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # `unaccent` is only STABLE, so it cannot back an index; this wrapper pins
    # the dictionary and is declared IMMUTABLE.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION immutable_unaccent(text) RETURNS text
        AS $$ SELECT public.unaccent('public.unaccent', $1) $$
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_attributes_gin ON nodes
        USING gin (attributes jsonb_path_ops)
        """
    )
    op.execute(
        "CREATE INDEX ix_nodes_tags_gin ON nodes USING gin (tags jsonb_path_ops)"
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_name_trgm ON nodes
        USING gin (immutable_unaccent(name) gin_trgm_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_description_trgm ON nodes
        USING gin (immutable_unaccent(description) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_nodes_description_trgm")
    op.execute("DROP INDEX IF EXISTS ix_nodes_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_nodes_tags_gin")
    op.execute("DROP INDEX IF EXISTS ix_nodes_attributes_gin")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
    # pg_trgm stays installed, as with `unaccent`: it may be shared.

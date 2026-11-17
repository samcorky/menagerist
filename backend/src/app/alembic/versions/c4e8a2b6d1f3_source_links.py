"""source links

Records which entity an import created from a source's key, with a hash per field
as last imported, so a source can be imported again.

Revision ID: c4e8a2b6d1f3
Revises: d8f3a1c6e2b9
Create Date: 2026-11-17 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4e8a2b6d1f3"
down_revision: str | None = "d8f3a1c6e2b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "source_links",
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "fields",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("imported_at", _TIMESTAMP, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_source_links_owner_source_kind_key",
        "source_links",
        ["owner_id", "source", "kind", "key"],
        unique=True,
    )
    op.create_index(
        "ix_source_links_owner_id_source", "source_links", ["owner_id", "source"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_links_owner_id_source", table_name="source_links")
    op.drop_index("uq_source_links_owner_source_kind_key", table_name="source_links")
    op.drop_table("source_links")

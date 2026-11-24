"""item imports

Keeps each CSV file uploaded to import: its status, the options it was queued
with, its progress and its result, so the worker can import it in the background
and its owner can watch. The file itself is stored on disk beside the media.

Revision ID: d8f2a6c4e1b7
Revises: e3a7c1f9b5d2
Create Date: 2026-11-24 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8f2a6c4e1b7"
down_revision: str | None = "e3a7c1f9b5d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    """Create `item_imports` and its indexes."""
    op.create_table(
        "item_imports",
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=True),
        sa.Column("grants", postgresql.JSONB(), nullable=True),
        sa.Column("progress", postgresql.JSONB(), nullable=True),
        sa.Column("outcome", postgresql.JSONB(), nullable=True),
        sa.Column("failure", sa.String(), nullable=True),
        sa.Column("queued_at", _TIMESTAMP, nullable=True),
        sa.Column("started_at", _TIMESTAMP, nullable=True),
        sa.Column("finished_at", _TIMESTAMP, nullable=True),
        sa.Column("expires_at", _TIMESTAMP, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("updated_at", _TIMESTAMP, nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_item_imports_owner_id_id", "item_imports", ["owner_id", "id"])
    op.create_index(
        "ix_item_imports_status_queued_at", "item_imports", ["status", "queued_at"]
    )
    op.create_index("ix_item_imports_expires_at", "item_imports", ["expires_at"])


def downgrade() -> None:
    """Drop `item_imports`."""
    op.drop_index("ix_item_imports_expires_at", table_name="item_imports")
    op.drop_index("ix_item_imports_status_queued_at", table_name="item_imports")
    op.drop_index("ix_item_imports_owner_id_id", table_name="item_imports")
    op.drop_table("item_imports")

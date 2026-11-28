"""collection_summary

A collection can store the totals shown above its items: a list of aggregate
measures. Null (the default, so every existing collection) means the totals are
chosen automatically from the item types it holds.

Revision ID: d4b8f2a6c0e3
Revises: c5e9a3f7b1d4
Create Date: 2026-11-28 14:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4b8f2a6c0e3"
down_revision: str | None = "c5e9a3f7b1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collections", "summary")

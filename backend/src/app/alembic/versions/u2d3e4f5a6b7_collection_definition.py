"""collection_definition

Revision ID: u2d3e4f5a6b7
Revises: t1c2d3e4f5a6
Create Date: 2026-10-17 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "u2d3e4f5a6b7"
down_revision: str | None = "t1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Null for manual collections, so existing rows need no backfill.
    op.add_column(
        "collections",
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collections", "definition")

"""make_node_type_nullable

Revision ID: b1c2d3e4f5a6
Revises: a3f81c2d9e04
Create Date: 2026-08-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a3f81c2d9e04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("nodes", "type", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    # Set any null types to a placeholder before restoring NOT NULL constraint.
    op.execute("UPDATE nodes SET type = 'uncategorised' WHERE type IS NULL")
    op.alter_column("nodes", "type", existing_type=sa.String(), nullable=False)

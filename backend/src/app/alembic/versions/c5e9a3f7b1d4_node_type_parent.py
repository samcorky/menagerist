"""node_type_parent

An item type may be a subtype of another, named by its slug. No parent is the
default, so every existing type stays top-level. A type cannot be its own parent;
the use cases keep the nesting one level deep.

Revision ID: c5e9a3f7b1d4
Revises: d8f2a6c4e1b7
Create Date: 2026-11-25 14:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5e9a3f7b1d4"
down_revision: str | None = "d8f2a6c4e1b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("node_types", sa.Column("parent", sa.String(), nullable=True))
    op.create_index("ix_node_types_parent", "node_types", ["parent"])
    op.create_check_constraint(
        "ck_node_types_not_own_parent",
        "node_types",
        "parent IS NULL OR parent <> slug",
    )


def downgrade() -> None:
    op.drop_constraint("ck_node_types_not_own_parent", "node_types", type_="check")
    op.drop_index("ix_node_types_parent", table_name="node_types")
    op.drop_column("node_types", "parent")

"""per_user_item_favourites

Moves the favourite flag off the item into one row per user and item, so each
person keeps their own. Existing favourites go to the item's owner.

Revision ID: b7c4e91a2d58
Revises: e6f7a8b9c0d1
Create Date: 2026-11-04 16:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c4e91a2d58"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create `node_favourites`, copy each flag to the owner, drop the column."""
    op.create_table(
        "node_favourites",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "node_id"),
    )
    op.create_index(
        op.f("ix_node_favourites_node_id"), "node_favourites", ["node_id"], unique=False
    )
    op.execute(
        """
        INSERT INTO node_favourites (user_id, node_id, created_at)
        SELECT owner_id, id, now() FROM nodes
        WHERE favourite AND owner_id IS NOT NULL
        """
    )
    op.drop_column("nodes", "favourite")


def downgrade() -> None:
    """Put the flag back on the item, set from its owner's favourite."""
    op.add_column(
        "nodes",
        sa.Column("favourite", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        """
        UPDATE nodes SET favourite = true WHERE EXISTS (
            SELECT 1 FROM node_favourites f
            WHERE f.node_id = nodes.id AND f.user_id = nodes.owner_id
        )
        """
    )
    op.drop_index(op.f("ix_node_favourites_node_id"), table_name="node_favourites")
    op.drop_table("node_favourites")

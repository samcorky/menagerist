"""create_collections

Revision ID: h9c0d1e2f3a4
Revises: g8b9c0d1e2f3
Create Date: 2026-10-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h9c0d1e2f3a4"
down_revision: str | None = "g8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = sa.text("deleted_at IS NULL")


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_collections_deleted_at"), "collections", ["deleted_at"], unique=False
    )
    op.create_index(
        "uq_collections_slug_live",
        "collections",
        ["slug"],
        unique=True,
        postgresql_where=_LIVE,
    )
    op.create_table(
        "collection_members",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"]),
        sa.PrimaryKeyConstraint("collection_id", "item_id"),
    )
    op.create_index(
        op.f("ix_collection_members_item_id"),
        "collection_members",
        ["item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_collection_members_item_id"), table_name="collection_members"
    )
    op.drop_table("collection_members")
    op.drop_index(
        "uq_collections_slug_live", table_name="collections", postgresql_where=_LIVE
    )
    op.drop_index(op.f("ix_collections_deleted_at"), table_name="collections")
    op.drop_table("collections")

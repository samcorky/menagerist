"""create_example_installations

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-10-06 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "g8b9c0d1e2f3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE = sa.text("status IN ('installing', 'installed')")


def upgrade() -> None:
    op.create_table(
        "example_installations",
        sa.Column("pack_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "entities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_example_installations_pack_id"),
        "example_installations",
        ["pack_id"],
        unique=False,
    )
    op.create_index(
        "uq_example_installations_active_pack",
        "example_installations",
        ["pack_id"],
        unique=True,
        postgresql_where=_ACTIVE,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_example_installations_active_pack",
        table_name="example_installations",
        postgresql_where=_ACTIVE,
    )
    op.drop_index(
        op.f("ix_example_installations_pack_id"), table_name="example_installations"
    )
    op.drop_table("example_installations")

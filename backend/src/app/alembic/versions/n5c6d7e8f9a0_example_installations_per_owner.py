"""example_installations_per_owner

Revision ID: n5c6d7e8f9a0
Revises: m4b5c6d7e8f9
Create Date: 2026-10-10 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n5c6d7e8f9a0"
down_revision: str | None = "m4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE = "status IN ('installing', 'installed')"


def upgrade() -> None:
    op.add_column(
        "example_installations", sa.Column("owner_id", sa.Uuid(), nullable=True)
    )
    op.drop_index(
        "uq_example_installations_active_pack",
        table_name="example_installations",
        postgresql_where=sa.text(_ACTIVE),
    )
    op.create_index(
        "uq_example_installations_active_pack",
        "example_installations",
        ["pack_id", "owner_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE),
    )
    op.create_index(
        "ix_example_installations_owner_id_id",
        "example_installations",
        ["owner_id", "id"],
    )


def downgrade() -> None:
    # Fails if two people hold the same active pack: remove one installation first.
    op.drop_index(
        "ix_example_installations_owner_id_id", table_name="example_installations"
    )
    op.drop_index(
        "uq_example_installations_active_pack",
        table_name="example_installations",
        postgresql_where=sa.text(_ACTIVE),
    )
    op.create_index(
        "uq_example_installations_active_pack",
        "example_installations",
        ["pack_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE),
    )
    op.drop_column("example_installations", "owner_id")

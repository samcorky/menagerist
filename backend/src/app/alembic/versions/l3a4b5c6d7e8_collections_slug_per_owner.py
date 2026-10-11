"""collections_slug_per_owner

Revision ID: l3a4b5c6d7e8
Revises: k2f3a4b5c6d7
Create Date: 2026-10-10 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l3a4b5c6d7e8"
down_revision: str | None = "k2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIVE = sa.text("deleted_at IS NULL")


def upgrade() -> None:
    op.drop_index(
        "uq_collections_slug_live", table_name="collections", postgresql_where=_LIVE
    )
    op.create_index(
        "uq_collections_slug_live",
        "collections",
        ["owner_id", "slug"],
        unique=True,
        postgresql_where=_LIVE,
    )
    op.create_index("ix_collections_owner_id", "collections", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_collections_owner_id", table_name="collections")
    op.drop_index(
        "uq_collections_slug_live", table_name="collections", postgresql_where=_LIVE
    )
    op.create_index(
        "uq_collections_slug_live",
        "collections",
        ["slug"],
        unique=True,
        postgresql_where=_LIVE,
    )

"""add_thumbnail_sha256_to_media_assets

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-09-14 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no backfill: existing thumbnails (generated before this
    # column existed) fall back to `sha256` for cache-key purposes until
    # they're next regenerated, at which point they get their own hash.
    op.add_column(
        "media_assets",
        sa.Column("thumbnail_sha256", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("media_assets", "thumbnail_sha256")

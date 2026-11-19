"""media thumbnail size

Keeps each thumbnail's width and height, so the item page can reserve a cover's
shape before the picture loads. Existing thumbnails stay null until
`menagerist media regenerate-thumbnails` makes them again.

Revision ID: e3a7c1f9b5d2
Revises: a1b2c7d4e9f5
Create Date: 2026-11-19 19:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3a7c1f9b5d2"
down_revision: str | None = "a1b2c7d4e9f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_assets", sa.Column("thumbnail_width", sa.Integer(), nullable=True)
    )
    op.add_column(
        "media_assets", sa.Column("thumbnail_height", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("media_assets", "thumbnail_height")
    op.drop_column("media_assets", "thumbnail_width")

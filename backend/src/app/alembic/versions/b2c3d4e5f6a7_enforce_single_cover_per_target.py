"""enforce_single_cover_per_target

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-15 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Partial index: only one attachment per (target_type, target_id) may hold
    # attribute_key='cover' at a time. NULL attribute_key rows are unrestricted.
    op.create_index(
        "uq_media_attachment_cover",
        "media_attachments",
        ["target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("attribute_key = 'cover'"),
    )


def downgrade() -> None:
    op.drop_index("uq_media_attachment_cover", table_name="media_attachments")

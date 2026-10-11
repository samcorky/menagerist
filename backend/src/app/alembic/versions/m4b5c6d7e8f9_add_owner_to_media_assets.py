"""add_owner_to_media_assets

Revision ID: m4b5c6d7e8f9
Revises: l3a4b5c6d7e8
Create Date: 2026-10-10 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m4b5c6d7e8f9"
down_revision: str | None = "l3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media_assets", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_index("ix_media_assets_owner_id_id", "media_assets", ["owner_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_media_assets_owner_id_id", table_name="media_assets")
    op.drop_column("media_assets", "owner_id")

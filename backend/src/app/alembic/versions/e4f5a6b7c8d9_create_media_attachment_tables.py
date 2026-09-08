"""create media_attachments polymorphic table

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_attachments",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("attribute_key", sa.String(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id",
            "target_type",
            "target_id",
            "attribute_key",
            name="uq_media_attachment",
        ),
    )
    op.create_index(
        op.f("ix_media_attachments_asset_id"),
        "media_attachments",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_media_attachments_target_type"),
        "media_attachments",
        ["target_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_media_attachments_target_id"),
        "media_attachments",
        ["target_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_media_attachments_target_id"),
        table_name="media_attachments",
    )
    op.drop_index(
        op.f("ix_media_attachments_target_type"),
        table_name="media_attachments",
    )
    op.drop_index(
        op.f("ix_media_attachments_asset_id"),
        table_name="media_attachments",
    )
    op.drop_table("media_attachments")

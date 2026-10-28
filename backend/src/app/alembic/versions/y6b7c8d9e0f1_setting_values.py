"""Saved instance and per-user setting values.

Revision ID: y6b7c8d9e0f1
Revises: x5a6b7c8d9e0
Create Date: 2026-10-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "y6b7c8d9e0f1"
down_revision: str | None = "x5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "setting_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_setting_values_instance",
        "setting_values",
        ["scope", "key"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )
    op.create_index(
        "uq_setting_values_owner",
        "setting_values",
        ["owner_id", "key"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_setting_values_owner", table_name="setting_values")
    op.drop_index("uq_setting_values_instance", table_name="setting_values")
    op.drop_table("setting_values")

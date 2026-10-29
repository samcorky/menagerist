"""The stored result of the latest release check.

Revision ID: z7c8d9e0f1a2
Revises: y6b7c8d9e0f1
Create Date: 2026-10-29 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "z7c8d9e0f1a2"
down_revision: str | None = "y6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "update_checks",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("latest_version", sa.String(), nullable=True),
        sa.Column("latest_url", sa.String(), nullable=True),
        sa.Column("latest_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_prerelease", sa.Boolean(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("update_checks")

"""update_check_release_title

Keeps the latest release's title beside its version. Rows stored before this
revision have none and are read back as the version until the next check.

Revision ID: c3d9a5f1b284
Revises: b7c4e91a2d58
Create Date: 2026-11-05 08:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d9a5f1b284"
down_revision: str | None = "b7c4e91a2d58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable `latest_title` column."""
    op.add_column(
        "update_checks", sa.Column("latest_title", sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Drop `latest_title`."""
    op.drop_column("update_checks", "latest_title")

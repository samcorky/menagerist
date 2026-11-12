"""update_check_edge_revision

Keeps the revision the published edge image was built from beside the release, so a
development build can be told whether it is the current edge. Rows stored before
this revision have none and are read back as unknown until the next check.

Revision ID: a7b3c2d1e4f5
Revises: f1a2b3c4d5e6
Create Date: 2026-11-12 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b3c2d1e4f5"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable `edge_revision` column."""
    op.add_column(
        "update_checks", sa.Column("edge_revision", sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Drop `edge_revision`."""
    op.drop_column("update_checks", "edge_revision")

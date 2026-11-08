"""job_run_progress

Adds a nullable `progress` column to `job_runs`, where a running job's latest
snapshot lives. It is cleared when a run succeeds and kept when one fails, so the
run shows where it stopped. The table stays `SKIP` in the backup table rules.

Revision ID: d4a1b6c8e3f2
Revises: c3d9a5f1b284
Create Date: 2026-11-07 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4a1b6c8e3f2"
down_revision: str | None = "c3d9a5f1b284"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable `progress` column."""
    op.add_column(
        "job_runs",
        sa.Column("progress", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Drop the `progress` column."""
    op.drop_column("job_runs", "progress")

"""device display mode

Records on a remembered browser whether it has signed in as the installed app,
so its label no longer depends on whichever of its sessions is newest. Existing
devices are backfilled from their sessions: a device with any `standalone`
session becomes `standalone`, otherwise it takes its newest session's mode.

Revision ID: a1b2c7d4e9f5
Revises: b4e8c2d6f1a3
Create Date: 2026-11-18 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c7d4e9f5"
down_revision: str | None = "b4e8c2d6f1a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("display_mode", sa.String(), nullable=True))
    # Installed wins over a browser tab, matching Device.seen()'s sticky rule.
    op.execute(
        """
        UPDATE devices AS d
        SET display_mode = 'standalone'
        WHERE EXISTS (
            SELECT 1 FROM sessions AS s
            WHERE s.device_id = d.id AND s.display_mode = 'standalone'
        )
        """
    )
    op.execute(
        """
        UPDATE devices AS d
        SET display_mode = newest.display_mode
        FROM (
            SELECT DISTINCT ON (device_id) device_id, display_mode
            FROM sessions
            WHERE device_id IS NOT NULL AND display_mode IS NOT NULL
            ORDER BY device_id, created_at DESC
        ) AS newest
        WHERE d.id = newest.device_id AND d.display_mode IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("devices", "display_mode")

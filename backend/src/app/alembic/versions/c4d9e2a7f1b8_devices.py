"""devices

Remembers signed-in browsers: a `devices` table holding only the hash of each
browser's device cookie, and `sessions.device_id` linking a session to the
browser it was started in. `sessions.display_mode` records whether the app ran
in a browser tab or installed. Existing sessions keep no device and no display
mode.

Revision ID: c4d9e2a7f1b8
Revises: b8e2d4f6a1c3
Create Date: 2026-11-14 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d9e2a7f1b8"
down_revision: str | None = "b8e2d4f6a1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", _TIMESTAMP, nullable=False),
        sa.Column("last_seen_at", _TIMESTAMP, nullable=False),
        sa.Column("expires_at", _TIMESTAMP, nullable=False),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("mobile", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])
    op.create_index("ix_devices_expires_at", "devices", ["expires_at"])
    op.add_column("sessions", sa.Column("device_id", sa.Uuid(), nullable=True))
    op.add_column("sessions", sa.Column("display_mode", sa.String(), nullable=True))
    op.create_foreign_key(
        "sessions_device_id_fkey",
        "sessions",
        "devices",
        ["device_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_sessions_device_id", "sessions", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_device_id", table_name="sessions")
    op.drop_constraint("sessions_device_id_fkey", "sessions", type_="foreignkey")
    op.drop_column("sessions", "display_mode")
    op.drop_column("sessions", "device_id")
    op.drop_index("ix_devices_expires_at", table_name="devices")
    op.drop_index("ix_devices_user_id", table_name="devices")
    op.drop_table("devices")

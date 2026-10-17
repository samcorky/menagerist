"""session_device_info

Revision ID: v3e4f5a6b7c8
Revises: u2d3e4f5a6b7
Create Date: 2026-10-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3e4f5a6b7c8"
down_revision: str | None = "u2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("user_agent", sa.String(), nullable=True))
    op.add_column("sessions", sa.Column("client_ip", sa.String(), nullable=True))
    op.add_column("sessions", sa.Column("client_platform", sa.String(), nullable=True))
    op.add_column("sessions", sa.Column("client_mobile", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "client_mobile")
    op.drop_column("sessions", "client_platform")
    op.drop_column("sessions", "client_ip")
    op.drop_column("sessions", "user_agent")

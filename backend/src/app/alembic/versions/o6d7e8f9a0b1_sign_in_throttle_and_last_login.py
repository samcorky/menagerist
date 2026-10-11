"""sign_in_throttle_and_last_login

Revision ID: o6d7e8f9a0b1
Revises: n5c6d7e8f9a0
Create Date: 2026-10-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o6d7e8f9a0b1"
down_revision: str | None = "n5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Failure counting moved to sign_in_attempts, keyed on hashes of username and IP.
    op.drop_column("users", "failed_attempts")
    op.drop_column("users", "failure_window_started_at")
    op.drop_column("users", "locked_until")
    op.create_table(
        "sign_in_attempts",
        sa.Column("key_type", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key_type", "key_hash"),
    )
    op.create_index(
        "ix_sign_in_attempts_window_start", "sign_in_attempts", ["window_start"]
    )


def downgrade() -> None:
    op.drop_index("ix_sign_in_attempts_window_start", table_name="sign_in_attempts")
    op.drop_table("sign_in_attempts")
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True)))
    op.add_column(
        "users", sa.Column("failure_window_started_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "users",
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("users", "failed_attempts", server_default=None)
    op.drop_column("users", "last_login_at")

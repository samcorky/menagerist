"""user avatars

Lets an account carry a picture: the version that names its stored files, where
it came from and when it was set. Existing accounts keep the initials default.

Revision ID: b4e8c2d6f1a3
Revises: c4e8a2b6d1f3
Create Date: 2026-11-16 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e8c2d6f1a3"
down_revision: str | None = "c4e8a2b6d1f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_version", sa.String(), nullable=True))
    op.add_column("users", sa.Column("avatar_source", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_updated_at")
    op.drop_column("users", "avatar_source")
    op.drop_column("users", "avatar_version")

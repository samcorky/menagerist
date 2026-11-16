"""device names

Lets a remembered browser carry a name chosen by its owner, such as "Sam's
phone". Existing devices stay unnamed.

Revision ID: d8f3a1c6e2b9
Revises: a7c3e9f1d2b4
Create Date: 2026-11-16 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8f3a1c6e2b9"
down_revision: str | None = "a7c3e9f1d2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "name")

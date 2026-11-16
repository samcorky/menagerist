"""edge_type_holder

Which end of a connection holds the other, for an item's contents and path:
`source` (Contains), `target` (Located in) or `none`. The starter types'
Located in and Part of read as the target holding the source.

Revision ID: a7c3e9f1d2b4
Revises: d5e1f3a8b2c9
Create Date: 2026-11-15 23:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9f1d2b4"
down_revision: str | None = "d5e1f3a8b2c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "edge_types",
        sa.Column("holder", sa.String(), nullable=False, server_default="none"),
    )
    op.create_check_constraint(
        "ck_edge_types_holder",
        "edge_types",
        "holder IN ('source', 'target', 'none') AND (holder = 'none' OR directional)",
    )
    op.execute(
        "UPDATE edge_types SET holder = 'target' "
        + "WHERE slug IN ('located-in', 'part-of') AND directional"
    )


def downgrade() -> None:
    op.drop_constraint("ck_edge_types_holder", "edge_types", type_="check")
    op.drop_column("edge_types", "holder")

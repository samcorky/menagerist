"""The shape of the recursive reach walk."""

import uuid

from app.modules.graph.adapters.persistence.reach_sql import walk
from app.shared_kernel.content_filter import ContentFilter


def test_walk_deduplicates_each_step_so_paths_cannot_multiply() -> None:
    """Each step is deduplicated as it is produced."""
    steps = walk(
        uuid.uuid4(),
        relationship="contains",
        direction="out",
        max_depth=25,
        scope=ContentFilter(user_id=uuid.uuid4()),
    )

    sql = str(steps.select().compile())

    # UNION ALL would revisit an item once per route to it: a ladder of
    # two-way branches 25 deep is about 33 million rows.
    assert "UNION ALL" not in sql
    assert "UNION" in sql

import re
import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.query import Cursor, ResolvedQuery, parse_query
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Select

pytestmark = pytest.mark.integration

OWNER = uuid.UUID(int=301)


class _Capture:
    """A session stand-in that records the statement instead of running it."""

    def __init__(self) -> None:
        self.statement: Select[Any] | None = None

    async def execute(self, statement: Select[Any]) -> _Capture:
        self.statement = statement
        return self

    def all(self) -> list[Any]:
        return []


async def _plan(
    db_session: AsyncSession,
    by: str,
    direction: str,
    cursor_value: str | float,
    *,
    mid: bool,
) -> str:
    query = parse_query({"v": 1, "where": None, "sort": [{"by": by, "dir": direction}]})
    resolved = ResolvedQuery(
        query=query,
        field_kinds=resolve_fields(query, {}).kinds,
        search_exclusions={},
        today=date(2026, 10, 15),
    )
    after = Cursor(sort_values=(cursor_value,), id=uuid.UUID(int=0)) if mid else None
    capture = _Capture()
    await SqlAlchemyNodeRepository(capture).search(  # type: ignore[arg-type]
        scope=ContentFilter.of(OWNER), resolved=resolved, after=after, limit=51
    )
    assert capture.statement is not None
    sql = str(
        capture.statement.compile(
            dialect=db_session.get_bind().dialect,
            compile_kwargs={"literal_binds": True},
        )
    )
    result = await db_session.execute(text(f"EXPLAIN {sql}"))
    return "\n".join(row[0] for row in result)


_CURSORS: dict[str, str | float] = {
    "name": "item 10000",
    "created": 1_700_010_000.5,
    "updated": 1_700_010_000.5,
}


@pytest.mark.parametrize("by", ["name", "created", "updated"])
@pytest.mark.parametrize(
    ("direction", "mid"),
    [("asc", False), ("desc", False), ("asc", True), ("desc", True)],
)
async def test_sort_is_served_by_the_index(
    db_session: AsyncSession, by: str, direction: str, mid: bool
) -> None:
    """Sorting by name or a timestamp reads an index in order, with no sort step."""
    await db_session.execute(
        text(
            """
            INSERT INTO nodes (id, owner_id, name, tags, attributes, favourite,
                               created_at, updated_at)
            SELECT gen_random_uuid(), :owner, 'Item ' || n, '[]'::jsonb,
                   '{}'::jsonb, false,
                   to_timestamp(1700000000 + n), to_timestamp(1700000000 + n)
            FROM generate_series(1, 20000) AS n
            """
        ),
        {"owner": OWNER},
    )
    await db_session.execute(text("ANALYZE nodes"))
    cursor_value = _CURSORS[by]
    plan = await _plan(db_session, by, direction, cursor_value, mid=mid)
    # Timestamps reuse the ascending index backwards, so ties need an
    # incremental sort; name has an index per direction and needs none.
    backward = by != "name" and direction == "desc"
    desc = by == "name" and direction == "desc"
    index = f"ix_nodes_owner_{by}_sort" + ("_desc" if desc else "")
    assert f"using {index} " in plan, plan
    full_sorts = [
        line
        for line in plan.splitlines()
        if re.match(r"\s*(->\s*)?Sort\s+\(cost", line)
    ]
    assert not full_sorts, plan
    if backward:
        assert "Index Scan Backward" in plan, plan
        assert "Incremental Sort" in plan, plan
        assert "Presorted Key" in plan, plan
    else:
        assert "Sort" not in plan, plan
    if mid:
        # The cursor must narrow the index scan, not only filter its rows.
        assert any(
            "Index Cond" in line and str(cursor_value).split(".")[0] in line
            for line in plan.splitlines()
        ), plan

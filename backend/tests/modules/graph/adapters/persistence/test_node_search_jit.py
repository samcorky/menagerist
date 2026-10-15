"""Text searches turn JIT off for their transaction only."""

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.query import ResolvedQuery, parse_query
from app.shared_kernel.access_scope import AccessScope

OWNER = uuid.UUID(int=212)
SCOPE = AccessScope.of(OWNER)
TEXT: dict[str, Any] = {
    "v": 1,
    "where": {"op": "and", "children": [{"kind": "text", "q": "alien"}]},
}
NESTED_TEXT: dict[str, Any] = {
    "v": 1,
    "where": {
        "op": "or",
        "children": [
            {"kind": "favourite", "value": True},
            {"op": "not", "children": [{"kind": "text", "q": "alien"}]},
        ],
    },
}
NO_TEXT: dict[str, Any] = {
    "v": 1,
    "where": {"op": "and", "children": [{"kind": "favourite", "value": True}]},
}


def _resolved(raw: dict[str, Any]) -> ResolvedQuery:
    query = parse_query(raw)
    return ResolvedQuery(
        query=query,
        field_kinds=resolve_fields(query, {}).kinds,
        search_exclusions={},
        today=date(2026, 10, 15),
    )


async def _jit(session: AsyncSession) -> str:
    return str((await session.execute(text("SHOW jit"))).scalar_one())


async def _run(repo: Any, how: str) -> None:  # noqa: ANN401
    resolved = _resolved(TEXT)
    if how == "search":
        await repo.search(scope=SCOPE, resolved=resolved, after=None, limit=5)
    elif how == "search_count":
        await repo.search_count(scope=SCOPE, resolved=resolved)
    elif how == "nested":
        await repo.search(
            scope=SCOPE, resolved=_resolved(NESTED_TEXT), after=None, limit=5
        )
    elif how == "list":
        await repo.list(scope=SCOPE, after=None, limit=5, q="alien")
    elif how == "count":
        await repo.count(scope=SCOPE, q="alien")


HOWS = ["search", "search_count", "nested", "list", "count"]


@pytest.mark.integration
@pytest.mark.parametrize("how", HOWS)
async def test_text_queries_turn_jit_off(db_session: AsyncSession, how: str) -> None:
    """Search, count, list and count with a text condition switch JIT off."""
    assert await _jit(db_session) == "on"
    await _run(SqlAlchemyNodeRepository(db_session), how)
    assert await _jit(db_session) == "off"


@pytest.mark.integration
async def test_queries_without_text_leave_jit_alone(db_session: AsyncSession) -> None:
    """Without a text condition the setting is untouched."""
    repo = SqlAlchemyNodeRepository(db_session)
    await db_session.execute(text("SET LOCAL jit = on"))
    resolved = _resolved(NO_TEXT)
    await repo.search(scope=SCOPE, resolved=resolved, after=None, limit=5)
    await repo.search_count(scope=SCOPE, resolved=resolved)
    await repo.list(scope=SCOPE, after=None, limit=5)
    await repo.count(scope=SCOPE)
    assert await _jit(db_session) == "on"


@pytest.mark.integration
async def test_jit_setting_does_not_outlive_the_transaction(postgres_url: str) -> None:
    """A real transaction on its own connection gets JIT back after it ends."""
    engine = create_async_engine(postgres_url)
    async with engine.connect() as connection:
        session = AsyncSession(bind=connection, expire_on_commit=False)
        await _run(SqlAlchemyNodeRepository(session), "search")
        assert await _jit(session) == "off"
        await session.commit()
        assert await _jit(session) == "on"
        await session.close()
    await engine.dispose()


@pytest.mark.parametrize("how", HOWS)
async def test_in_memory_adapter_is_unaffected(how: str) -> None:
    """The in-memory adapter runs the same queries with no database setting."""
    await _run(InMemoryNodeRepository(), how)

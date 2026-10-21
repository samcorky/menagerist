"""Tests for ValidateQuery and count_matching."""

import uuid
from datetime import date
from typing import Any

import pytest

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.prepare_query import count_matching
from app.modules.graph.application.validate_query import (
    ValidateQuery,
    ValidateQueryQuery,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import InvalidQueryError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"rating": {"type": "number", "x-menagerist": {"kind": "rating"}}},
}
OWNER = uuid.UUID(int=1)
OTHER = uuid.UUID(int=2)


async def _repos(count: int = 3) -> GraphRepos:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=SCHEMA)
    )
    for index in range(count):
        await repos.nodes.add(
            Node.create(
                owner_id=OWNER,
                name=f"Film {index}",
                type="film",
                attributes={"rating": index},
            )
        )
    await repos.nodes.add(Node.create(owner_id=OTHER, name="Theirs", type="film"))
    return repos


def _rating_at_least(value: int, key: str = "rating") -> dict[str, Any]:
    return {
        "v": 1,
        "where": {
            "op": "and",
            "children": [
                {
                    "kind": "field",
                    "type": "film",
                    "key": key,
                    "op": ">=",
                    "value": value,
                }
            ],
        },
    }


async def _validate(repos: GraphRepos, query: dict[str, Any]) -> Any:  # noqa: ANN401
    return await ValidateQuery(repos).handle(
        ValidateQueryQuery(query=query), SYSTEM_ACTOR
    )


async def test_validate_returns_no_warnings_for_a_live_query() -> None:
    """A query on existing fields validates cleanly."""
    result = await _validate(await _repos(), _rating_at_least(1))
    assert result.warnings == []


async def test_validate_warns_about_a_stale_field() -> None:
    """A removed field is a warning, not an error."""
    result = await _validate(await _repos(), _rating_at_least(1, key="gone"))
    assert [w.path for w in result.warnings] == ["where.children[0]"]


async def test_validate_raises_with_the_path_of_a_malformed_query() -> None:
    """A malformed query raises InvalidQueryError carrying its path."""
    with pytest.raises(InvalidQueryError) as caught:
        await _validate(await _repos(), {"v": 1, "where": {"op": "xor"}})
    assert caught.value.path.startswith("where")


async def test_count_matches_only_the_scopes_items() -> None:
    """The count covers the scope's items and never another owner's."""
    repos = await _repos(3)
    query = {"v": 1, "where": None}
    mine = await count_matching(repos, query, ContentFilter.of(OWNER), cap=10)
    theirs = await count_matching(repos, query, ContentFilter.of(OTHER), cap=10)
    assert (mine, theirs) == ((3, False), (1, False))


async def test_count_applies_the_conditions() -> None:
    """Conditions narrow the count."""
    repos = await _repos(3)
    got = await count_matching(
        repos, _rating_at_least(1), ContentFilter.of(OWNER), cap=10
    )
    assert got == (2, False)


async def test_count_is_capped() -> None:
    """Above the cap the count stops at the cap and says so."""
    repos = await _repos(5)
    query = {"v": 1, "where": None}
    assert await count_matching(repos, query, ContentFilter.of(OWNER), cap=3) == (
        3,
        True,
    )
    assert await count_matching(repos, query, ContentFilter.of(OWNER), cap=5) == (
        5,
        False,
    )


async def test_count_of_a_stale_field_matches_nothing() -> None:
    """A stale condition matches nothing and does not raise."""
    repos = await _repos(3)
    got = await count_matching(
        repos, _rating_at_least(0, key="gone"), ContentFilter.of(OWNER), cap=10
    )
    assert got == (0, False)


async def test_count_uses_the_given_clock() -> None:
    """Relative dates resolve against the supplied clock."""
    repos = await _repos(1)
    query = {"v": 1, "where": None}
    got = await count_matching(
        repos, query, ContentFilter.of(OWNER), cap=10, today=lambda: date(2026, 1, 1)
    )
    assert got == (1, False)


async def test_count_default_clock_is_utc_today() -> None:
    """Without a clock the count still resolves."""
    repos = await _repos(1)
    got = await count_matching(repos, {"v": 1}, ContentFilter.of(OWNER), cap=10)
    assert got == (1, False)


async def test_count_raises_for_a_malformed_query() -> None:
    """A malformed query raises; the bridge decides what to do with it."""
    with pytest.raises(InvalidQueryError):
        await count_matching(
            await _repos(),
            {"v": 1, "where": {"op": "xor"}},
            ContentFilter.of(OWNER),
            cap=3,
        )


async def test_count_without_a_cap_is_exact() -> None:
    """`cap=None` counts every match and is never flagged as capped."""
    repos = await _repos(5)
    query = {"v": 1, "where": None}
    got = await count_matching(repos, query, ContentFilter.of(OWNER), cap=None)
    assert got == (5, False)

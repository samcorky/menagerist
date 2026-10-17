"""Integration tests for the collections-to-graph definition bridges."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.entrypoints.api.shared.bridges.collection_definitions import (
    GraphDefinitionChecker,
)
from app.entrypoints.api.shared.collection_items import GraphItemLookup
from app.modules.collections.domain.errors import InvalidDefinitionError
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.access_scope import AccessScope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

ME = uuid.UUID(int=1)
THEM = uuid.UUID(int=2)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"rating": {"type": "number", "x-menagerist": {"kind": "rating"}}},
}


def _at_least(value: int, key: str = "rating") -> dict[str, Any]:
    cond = {"kind": "field", "type": "film", "key": key, "op": ">=", "value": value}
    return {"v": 1, "where": {"op": "and", "children": [cond]}}


async def _seed(
    session: AsyncSession,
) -> tuple[GraphItemLookup, GraphDefinitionChecker]:
    repos = build_graph_repos(session)
    await repos.node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=SCHEMA)
    )
    for owner, rating in ((ME, 1), (ME, 3), (THEM, 5)):
        await repos.nodes.add(
            Node.create(
                owner_id=owner,
                name=f"Film {rating}",
                type="film",
                attributes={"rating": rating},
            )
        )
    return GraphItemLookup(repos), GraphDefinitionChecker(repos)


async def test_count_applies_conditions_in_the_callers_scope(
    db_session: AsyncSession,
) -> None:
    """Another owner's items are never counted."""
    lookup, _ = await _seed(db_session)

    assert await lookup.count_matching(_at_least(1), AccessScope.of(ME), cap=10) == (
        2,
        False,
    )
    assert await lookup.count_matching(_at_least(1), AccessScope.of(THEM), cap=10) == (
        1,
        False,
    )


async def test_count_is_capped(db_session: AsyncSession) -> None:
    """The count stops at the cap and says so."""
    lookup, _ = await _seed(db_session)

    got = await lookup.count_matching(_at_least(0), AccessScope.of(ME), cap=1)

    assert got == (1, True)


async def test_empty_where_matches_everything(db_session: AsyncSession) -> None:
    """A definition without conditions counts every visible item."""
    lookup, _ = await _seed(db_session)

    got = await lookup.count_matching(
        {"v": 1, "where": None}, AccessScope.of(ME), cap=9
    )

    assert got == (2, False)


async def test_count_of_a_stale_field_is_zero_without_raising(
    db_session: AsyncSession,
) -> None:
    """A removed field matches nothing."""
    lookup, _ = await _seed(db_session)

    got = await lookup.count_matching(
        _at_least(0, key="gone"), AccessScope.of(ME), cap=10
    )

    assert got == (0, False)


async def test_count_of_an_unreadable_definition_is_zero_without_raising(
    db_session: AsyncSession,
) -> None:
    """A malformed stored definition is logged, not a 500."""
    lookup, _ = await _seed(db_session)

    got = await lookup.count_matching(
        {"v": 1, "where": {"op": "xor"}}, AccessScope.of(ME), cap=10
    )

    assert got == (0, False)


async def test_check_reports_stale_fields_as_warnings(
    db_session: AsyncSession,
) -> None:
    """A stale field is accepted and reported with its path."""
    _, checker = await _seed(db_session)

    warnings = await checker.check(_at_least(0, key="gone"), AccessScope.of(ME))

    assert [w.path for w in warnings] == ["where.children[0]"]
    assert await checker.check(_at_least(0), AccessScope.of(ME)) == []


async def test_check_translates_a_bad_definition_into_a_collections_error(
    db_session: AsyncSession,
) -> None:
    """The path survives and the message is not prefixed twice."""
    _, checker = await _seed(db_session)

    with pytest.raises(InvalidDefinitionError) as caught:
        await checker.check({"v": 1, "where": {"op": "xor"}}, AccessScope.of(ME))

    assert caught.value.path.startswith("where")
    assert str(caught.value).count(caught.value.path) == 1

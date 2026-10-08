"""Integration tests for the collections-to-graph item lookup bridge."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.collection_items import GraphItemLookup
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.domain.node import Node

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _lookup_with_nodes(
    session: AsyncSession, count: int, *, deleted: int = 0
) -> tuple[GraphItemLookup, list[Node]]:
    """Store `count` nodes, soft-deleting the first `deleted` of them."""
    repos = build_graph_repos(session)
    nodes = [Node.create(name=f"Item {i}", type=None) for i in range(count)]
    for index, node in enumerate(nodes):
        if index < deleted:
            node.soft_delete()
        await repos.nodes.add(node)
    return GraphItemLookup(repos), nodes


async def test_returns_only_live_items_among_the_given_ids(
    db_session: AsyncSession,
) -> None:
    """Unknown and soft-deleted ids are dropped from the result."""
    lookup, nodes = await _lookup_with_nodes(db_session, 4, deleted=1)

    result = await lookup.live_ids([*(n.id for n in nodes), uuid.uuid7()])

    assert result == {n.id for n in nodes[1:]}


async def test_empty_input_returns_an_empty_set(db_session: AsyncSession) -> None:
    """No ids means no live ids."""
    lookup, _ = await _lookup_with_nodes(db_session, 1)

    assert await lookup.live_ids([]) == set()


async def test_handles_more_ids_than_one_chunk(db_session: AsyncSession) -> None:
    """More than 1000 ids are looked up in chunks and unioned."""
    lookup, nodes = await _lookup_with_nodes(db_session, 1105)

    result = await lookup.live_ids([n.id for n in nodes])

    assert result == {n.id for n in nodes}


async def test_duplicate_ids_are_collapsed(db_session: AsyncSession) -> None:
    """Repeating an id does not change the result."""
    lookup, nodes = await _lookup_with_nodes(db_session, 1)

    assert await lookup.live_ids([nodes[0].id, nodes[0].id]) == {nodes[0].id}

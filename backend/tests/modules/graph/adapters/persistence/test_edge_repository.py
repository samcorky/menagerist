import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.edge_repository import (
    SqlAlchemyEdgeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _make_node(db_session: AsyncSession) -> Node:
    node = Node.create(name="Alien", type="film")
    await SqlAlchemyNodeRepository(db_session).add(node)
    return node


async def _make_edge(db_session: AsyncSession) -> Edge:
    source = await _make_node(db_session)
    target = await _make_node(db_session)
    edge = Edge.create(source_id=source.id, target_id=target.id, type="related-to")
    await SqlAlchemyEdgeRepository(db_session).add(edge)
    return edge


async def test_add_and_get_round_trips(db_session: AsyncSession) -> None:
    """An edge added to the repository can be retrieved by id."""
    repository = SqlAlchemyEdgeRepository(db_session)
    edge = await _make_edge(db_session)

    result = await repository.get(edge.id)

    assert result is not None
    assert result.id == edge.id
    assert result.source_id == edge.source_id
    assert result.target_id == edge.target_id
    assert result.type == edge.type
    assert result.attributes == edge.attributes


async def test_get_returns_none_for_missing_edge(db_session: AsyncSession) -> None:
    """get() returns None for an id that was never added."""
    repository = SqlAlchemyEdgeRepository(db_session)

    assert await repository.get(uuid.uuid4()) is None


async def test_get_returns_none_for_a_soft_deleted_edge(
    db_session: AsyncSession,
) -> None:
    """get() treats a soft-deleted edge as if it doesn't exist."""
    repository = SqlAlchemyEdgeRepository(db_session)
    edge = await _make_edge(db_session)

    edge.soft_delete()
    await repository.save(edge)

    assert await repository.get(edge.id) is None


async def test_save_persists_changes_to_an_existing_edge(
    db_session: AsyncSession,
) -> None:
    """save() overwrites the stored edge with the given instance."""
    repository = SqlAlchemyEdgeRepository(db_session)
    edge = await _make_edge(db_session)

    edge.update(attributes={"since": "1979"})
    await repository.save(edge)

    result = await repository.get(edge.id)
    assert result is not None
    assert result.attributes == {"since": "1979"}


async def test_list_orders_by_id_ascending(db_session: AsyncSession) -> None:
    """list() returns edges ordered by id ascending, regardless of insert order."""
    repository = SqlAlchemyEdgeRepository(db_session)
    edges = [await _make_edge(db_session) for _ in range(3)]

    result = await repository.list(after=None, limit=10)

    assert [e.id for e in result] == sorted(e.id for e in edges)


async def test_list_excludes_soft_deleted_edges(db_session: AsyncSession) -> None:
    """list() omits soft-deleted edges."""
    repository = SqlAlchemyEdgeRepository(db_session)
    kept = await _make_edge(db_session)
    deleted = await _make_edge(db_session)

    deleted.soft_delete()
    await repository.save(deleted)

    result = await repository.list(after=None, limit=10)

    assert [e.id for e in result] == [kept.id]


async def test_list_for_node_returns_edges_touching_the_node_either_direction(
    db_session: AsyncSession,
) -> None:
    """list_for_node() returns edges where the node is either source or target."""
    repository = SqlAlchemyEdgeRepository(db_session)
    node = await _make_node(db_session)
    other_a = await _make_node(db_session)
    other_b = await _make_node(db_session)
    outgoing = Edge.create(source_id=node.id, target_id=other_a.id, type="owns")
    incoming = Edge.create(source_id=other_b.id, target_id=node.id, type="owned-by")
    await repository.add(outgoing)
    await repository.add(incoming)
    unrelated = await _make_edge(db_session)

    result = await repository.list_for_node(node.id, after=None, limit=10)

    assert {e.id for e in result} == {outgoing.id, incoming.id}
    assert unrelated.id not in {e.id for e in result}


async def test_list_for_node_respects_after_and_limit(
    db_session: AsyncSession,
) -> None:
    """list_for_node() paginates using after/limit."""
    repository = SqlAlchemyEdgeRepository(db_session)
    node = await _make_node(db_session)
    edges = []
    for _ in range(4):
        target = await _make_node(db_session)
        edge = Edge.create(source_id=node.id, target_id=target.id, type="owns")
        await repository.add(edge)
        edges.append(edge)
    edges.sort(key=lambda e: e.id)

    page = await repository.list_for_node(node.id, after=edges[0].id, limit=2)

    assert [e.id for e in page] == [e.id for e in edges[1:3]]

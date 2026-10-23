import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from app.modules.graph.adapters.persistence.edge_repository import (
    SqlAlchemyEdgeRepository,
)
from app.modules.graph.adapters.persistence.models import EdgeModel, NodeModel
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_OWNER = uuid.UUID(int=1)


async def _node(session: AsyncSession) -> Node:
    node = Node.create(owner_id=_OWNER, name="Alien", type="film")
    await SqlAlchemyNodeRepository(session).add(node)
    return node


async def _edge(session: AsyncSession, source: Node, target: Node) -> Edge:
    edge = Edge.create(
        owner_id=_OWNER, source_id=source.id, target_id=target.id, type="related-to"
    )
    await SqlAlchemyEdgeRepository(session).add(edge)
    return edge


async def _ids(session: AsyncSession, model: type[NodeModel] | type[EdgeModel]) -> set:  # type: ignore[type-arg]
    """Row ids read straight from the table, so soft-deleted rows show."""
    return set((await session.execute(select(model.id))).scalars())


async def _count(session: AsyncSession) -> int:
    stmt = select(func.count()).select_from(NodeModel)
    return (await session.execute(stmt)).scalar_one()


async def test_purging_connections_then_the_node_respects_foreign_keys(
    db_session: AsyncSession,
) -> None:
    """Both directions, live and soft-deleted, go first; another link survives."""
    nodes, edges = (
        SqlAlchemyNodeRepository(db_session),
        SqlAlchemyEdgeRepository(db_session),
    )
    a, b, c = await _node(db_session), await _node(db_session), await _node(db_session)
    outgoing, incoming = await _edge(db_session, a, b), await _edge(db_session, c, a)
    soft = await _edge(db_session, a, c)
    soft.soft_delete()
    await edges.save(soft)
    other = await _edge(db_session, b, c)
    a.soft_delete()
    await nodes.save(a)

    await edges.purge_for_node(a.id)
    await nodes.purge(a.id)

    assert a.id not in await _ids(db_session, NodeModel)
    assert {outgoing.id, incoming.id, soft.id}.isdisjoint(
        await _ids(db_session, EdgeModel)
    )
    assert other.id in await _ids(db_session, EdgeModel)
    assert {b.id, c.id} <= await _ids(db_session, NodeModel)


async def test_purge_edge_removes_the_row_even_when_soft_deleted(
    db_session: AsyncSession,
) -> None:
    """A soft-deleted edge is gone from the table, its items stay."""
    edges = SqlAlchemyEdgeRepository(db_session)
    a, b = await _node(db_session), await _node(db_session)
    edge = await _edge(db_session, a, b)
    edge.soft_delete()
    await edges.save(edge)

    await edges.purge(edge.id)

    assert edge.id not in await _ids(db_session, EdgeModel)
    assert {a.id, b.id} <= await _ids(db_session, NodeModel)


async def test_purging_an_unknown_id_is_a_no_op(db_session: AsyncSession) -> None:
    """Nothing is deleted and nothing raises."""
    a = await _node(db_session)
    before = (
        await db_session.execute(select(func.count()).select_from(NodeModel))
    ).scalar_one()

    await SqlAlchemyEdgeRepository(db_session).purge(uuid.uuid7())
    await SqlAlchemyEdgeRepository(db_session).purge_for_node(uuid.uuid7())
    await SqlAlchemyNodeRepository(db_session).purge(uuid.uuid7())

    after = (
        await db_session.execute(select(func.count()).select_from(NodeModel))
    ).scalar_one()
    assert after == before
    assert a.id in await _ids(db_session, NodeModel)

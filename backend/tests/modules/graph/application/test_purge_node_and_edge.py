import uuid

from app.entrypoints.api.shared.access_guard import get_access_guard
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
from app.modules.graph.application.purge_edge import PurgeEdge, PurgeEdgeCommand
from app.modules.graph.application.purge_node import PurgeNode, PurgeNodeCommand
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

OWNER = uuid.UUID(int=1)


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _node(repos: GraphRepos, name: str) -> Node:
    node = Node.create(owner_id=OWNER, name=name, type=None)
    await repos.nodes.add(node)
    return node


async def _edge(repos: GraphRepos, source: Node, target: Node) -> Edge:
    edge = Edge.create(
        owner_id=OWNER, source_id=source.id, target_id=target.id, type="knows"
    )
    await repos.edges.add(edge)
    return edge


async def test_purge_node_removes_it_and_its_connections_only() -> None:
    """A soft-deleted node and both its connections go; others' links survive."""
    repos = _repos()
    a, b, c = [await _node(repos, n) for n in "abc"]
    outgoing, incoming = await _edge(repos, a, b), await _edge(repos, c, a)
    deleted_link = await _edge(repos, a, c)
    deleted_link.soft_delete()
    await repos.edges.save(deleted_link)
    other = await _edge(repos, b, c)
    a.soft_delete()
    await repos.nodes.save(a)
    uow = InMemoryUnitOfWork(repos)

    await PurgeNode(uow, get_access_guard()).handle(
        PurgeNodeCommand(node_id=a.id), SYSTEM_ACTOR
    )

    everyone = ContentFilter.everyone()
    assert uow.committed is True
    assert a.id not in repos.nodes._nodes  # type: ignore[attr-defined]
    assert {e.id for e in repos.edges._edges.values()} == {other.id}  # type: ignore[attr-defined]
    assert await repos.nodes.get(b.id, scope=everyone) is b
    assert await repos.edges.get(outgoing.id, scope=everyone) is None
    assert await repos.edges.get(incoming.id, scope=everyone) is None


async def test_purge_node_with_an_unknown_id_is_a_no_op() -> None:
    """A repeat, or an id that never existed, changes nothing and does not raise."""
    repos = _repos()
    keeper = await _node(repos, "keeper")
    uow = InMemoryUnitOfWork(repos)

    await PurgeNode(uow, get_access_guard()).handle(
        PurgeNodeCommand(node_id=uuid.uuid7()), SYSTEM_ACTOR
    )

    assert await repos.nodes.get(keeper.id, scope=ContentFilter.everyone()) is keeper


async def test_purge_edge_removes_that_edge_only() -> None:
    """Purging one connection leaves the items and other connections."""
    repos = _repos()
    a, b = await _node(repos, "a"), await _node(repos, "b")
    gone, kept = await _edge(repos, a, b), await _edge(repos, b, a)
    gone.soft_delete()
    await repos.edges.save(gone)
    uow = InMemoryUnitOfWork(repos)

    await PurgeEdge(uow, get_access_guard()).handle(
        PurgeEdgeCommand(edge_id=gone.id), SYSTEM_ACTOR
    )

    assert uow.committed is True
    assert set(repos.edges._edges) == {kept.id}  # type: ignore[attr-defined]
    assert set(repos.nodes._nodes) == {a.id, b.id}  # type: ignore[attr-defined]


async def test_purge_edge_with_an_unknown_id_is_a_no_op() -> None:
    """An id that is already gone does not raise."""
    uow = InMemoryUnitOfWork(_repos())

    await PurgeEdge(uow, get_access_guard()).handle(
        PurgeEdgeCommand(edge_id=uuid.uuid7()), SYSTEM_ACTOR
    )

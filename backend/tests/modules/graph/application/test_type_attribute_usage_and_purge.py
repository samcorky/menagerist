import uuid

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
from app.modules.graph.application import purge_node_type_attribute
from app.modules.graph.application.count_edge_type_attribute_usage import (
    CountEdgeTypeAttributeUsage,
    CountEdgeTypeAttributeUsageQuery,
)
from app.modules.graph.application.count_node_type_attribute_usage import (
    CountNodeTypeAttributeUsage,
    CountNodeTypeAttributeUsageQuery,
)
from app.modules.graph.application.purge_edge_type_attribute import (
    PurgeEdgeTypeAttribute,
    PurgeEdgeTypeAttributeCommand,
)
from app.modules.graph.application.purge_node_type_attribute import (
    PurgeNodeTypeAttribute,
    PurgeNodeTypeAttributeCommand,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError, NodeTypeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def _node_setup() -> tuple[GraphRepos, NodeType, list[Node]]:
    repos = _repos()
    node_type = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(node_type)
    nodes = [
        Node.create(name="A", type="film", attributes={"old": 1, "keep": "a"}),
        Node.create(name="B", type="film", attributes={"keep": "b"}),
        Node.create(name="C", type="film", attributes={"old": 3}),
        Node.create(name="D", type="book", attributes={"old": 4}),
    ]
    deleted = Node.create(name="E", type="film", attributes={"old": 5})
    deleted.soft_delete()
    for node in [*nodes, deleted]:
        await repos.nodes.add(node)
    return repos, node_type, nodes


async def _edge_setup() -> tuple[GraphRepos, EdgeType, list[Edge]]:
    repos = _repos()
    edge_type = EdgeType.create(slug="owns", label="Owns")
    await repos.edge_types.add(edge_type)
    source, target = uuid.uuid4(), uuid.uuid4()
    edges = [
        Edge.create(
            source_id=source, target_id=target, type="owns", attributes={"old": 1}
        ),
        Edge.create(source_id=source, target_id=target, type="owns", attributes={}),
        Edge.create(
            source_id=source, target_id=target, type="likes", attributes={"old": 3}
        ),
    ]
    for edge in edges:
        await repos.edges.add(edge)
    return repos, edge_type, edges


async def test_count_node_type_attribute_usage_counts_only_that_type() -> None:
    """Only live nodes of the type that hold the key are counted."""
    repos, node_type, _ = await _node_setup()

    count = await CountNodeTypeAttributeUsage(repos).handle(
        CountNodeTypeAttributeUsageQuery(node_type_id=node_type.id, key="old"),
        SYSTEM_ACTOR,
    )

    assert count == 2


async def test_count_node_type_attribute_usage_raises_for_missing_type() -> None:
    """An unknown node type id is a not-found error."""
    with pytest.raises(NodeTypeNotFoundError):
        await CountNodeTypeAttributeUsage(_repos()).handle(
            CountNodeTypeAttributeUsageQuery(node_type_id=uuid.uuid4(), key="old"),
            SYSTEM_ACTOR,
        )


async def test_count_edge_type_attribute_usage_counts_only_that_type() -> None:
    """Only live edges of the type that hold the key are counted."""
    repos, edge_type, _ = await _edge_setup()

    count = await CountEdgeTypeAttributeUsage(repos).handle(
        CountEdgeTypeAttributeUsageQuery(edge_type_id=edge_type.id, key="old"),
        SYSTEM_ACTOR,
    )

    assert count == 1


async def test_count_edge_type_attribute_usage_raises_for_missing_type() -> None:
    """An unknown edge type id is a not-found error."""
    with pytest.raises(EdgeTypeNotFoundError):
        await CountEdgeTypeAttributeUsage(_repos()).handle(
            CountEdgeTypeAttributeUsageQuery(edge_type_id=uuid.uuid4(), key="old"),
            SYSTEM_ACTOR,
        )


async def test_purge_node_type_attribute_removes_key_and_touches_nodes() -> None:
    """The key goes from every node of the type; other data and types are kept."""
    repos, node_type, nodes = await _node_setup()
    before = {node.id: node.updated_at for node in nodes}
    uow = InMemoryUnitOfWork(repos)

    purged = await PurgeNodeTypeAttribute(uow).handle(
        PurgeNodeTypeAttributeCommand(node_type_id=node_type.id, key="old"),
        SYSTEM_ACTOR,
    )

    assert purged == 2
    assert uow.committed is True
    a, b, c, d = nodes
    assert a.attributes == {"keep": "a"}
    assert c.attributes == {}
    assert a.updated_at > before[a.id]
    assert c.updated_at > before[c.id]
    assert b.updated_at == before[b.id]
    assert d.attributes == {"old": 4}


async def test_purge_node_type_attribute_pages_through_all_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """More nodes than one page are all purged."""
    monkeypatch.setattr(purge_node_type_attribute, "_PAGE_SIZE", 2)
    repos, node_type, _ = await _node_setup()
    for i in range(3):
        await repos.nodes.add(
            Node.create(name=f"X{i}", type="film", attributes={"old": i})
        )

    purged = await PurgeNodeTypeAttribute(InMemoryUnitOfWork(repos)).handle(
        PurgeNodeTypeAttributeCommand(node_type_id=node_type.id, key="old"),
        SYSTEM_ACTOR,
    )

    assert purged == 5
    assert await repos.nodes.count_with_attribute("film", "old") == 0


async def test_purge_node_type_attribute_raises_for_missing_type() -> None:
    """An unknown node type id is a not-found error."""
    with pytest.raises(NodeTypeNotFoundError):
        await PurgeNodeTypeAttribute(InMemoryUnitOfWork(_repos())).handle(
            PurgeNodeTypeAttributeCommand(node_type_id=uuid.uuid4(), key="old"),
            SYSTEM_ACTOR,
        )


async def test_purge_edge_type_attribute_removes_key() -> None:
    """The key goes from every edge of the type; other types are untouched."""
    repos, edge_type, edges = await _edge_setup()
    uow = InMemoryUnitOfWork(repos)

    purged = await PurgeEdgeTypeAttribute(uow).handle(
        PurgeEdgeTypeAttributeCommand(edge_type_id=edge_type.id, key="old"),
        SYSTEM_ACTOR,
    )

    assert purged == 1
    assert uow.committed is True
    assert edges[0].attributes == {}
    assert edges[2].attributes == {"old": 3}


async def test_purge_edge_type_attribute_raises_for_missing_type() -> None:
    """An unknown edge type id is a not-found error."""
    with pytest.raises(EdgeTypeNotFoundError):
        await PurgeEdgeTypeAttribute(InMemoryUnitOfWork(_repos())).handle(
            PurgeEdgeTypeAttributeCommand(edge_type_id=uuid.uuid4(), key="old"),
            SYSTEM_ACTOR,
        )

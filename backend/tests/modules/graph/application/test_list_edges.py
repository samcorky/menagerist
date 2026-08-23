import uuid

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.application.list_edges import ListEdges, ListEdgesQuery
from app.modules.graph.domain.edge import Edge
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_list_edges_returns_all_edges() -> None:
    """ListEdges without node_id returns every edge."""
    repository = InMemoryEdgeRepository()
    edges = [
        Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
        for _ in range(3)
    ]
    for edge in edges:
        await repository.add(edge)
    use_case = ListEdges(repository)

    result = await use_case.handle(ListEdgesQuery(), SYSTEM_ACTOR)

    assert result == sorted(edges, key=lambda edge: edge.id)


async def test_list_edges_filters_by_node_id() -> None:
    """ListEdges with node_id delegates to list_for_node."""
    repository = InMemoryEdgeRepository()
    node_id = uuid.uuid4()
    touching = Edge.create(source_id=node_id, target_id=uuid.uuid4(), type="owns")
    unrelated = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
    await repository.add(touching)
    await repository.add(unrelated)
    use_case = ListEdges(repository)

    result = await use_case.handle(ListEdgesQuery(node_id=node_id), SYSTEM_ACTOR)

    assert result == [touching]

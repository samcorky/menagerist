import uuid

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
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.application.list_edges import ListEdges, ListEdgesQuery
from app.modules.graph.domain.edge import Edge
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_uow(edges: InMemoryEdgeRepository) -> GraphUnitOfWork:
    return create_in_memory_graph_uow(
        GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=edges,
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
    )


async def test_list_edges_returns_all_edges() -> None:
    """ListEdges without node_id returns every edge."""
    edges = InMemoryEdgeRepository()
    items = [
        Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
        for _ in range(3)
    ]
    for edge in items:
        await edges.add(edge)
    use_case = ListEdges(_make_uow(edges))

    result = await use_case.handle(ListEdgesQuery(), SYSTEM_ACTOR)

    assert result == sorted(items, key=lambda e: e.id)


async def test_list_edges_filters_by_node_id() -> None:
    """ListEdges with node_id delegates to list_for_node."""
    edges = InMemoryEdgeRepository()
    node_id = uuid.uuid4()
    touching = Edge.create(source_id=node_id, target_id=uuid.uuid4(), type="owns")
    unrelated = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
    await edges.add(touching)
    await edges.add(unrelated)
    use_case = ListEdges(_make_uow(edges))

    result = await use_case.handle(ListEdgesQuery(node_id=node_id), SYSTEM_ACTOR)

    assert result == [touching]

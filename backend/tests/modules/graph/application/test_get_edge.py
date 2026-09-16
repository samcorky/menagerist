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
from app.modules.graph.application.get_edge import GetEdge, GetEdgeQuery
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import EdgeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_repos(edges: InMemoryEdgeRepository) -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=edges,
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_get_edge_returns_existing_edge() -> None:
    """GetEdge returns the edge when it exists."""
    edges = InMemoryEdgeRepository()
    edge = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
    await edges.add(edge)
    use_case = GetEdge(_make_repos(edges))

    result = await use_case.handle(GetEdgeQuery(edge_id=edge.id), SYSTEM_ACTOR)

    assert result is edge


async def test_get_edge_raises_when_missing() -> None:
    """GetEdge raises EdgeNotFoundError when the edge doesn't exist."""
    use_case = GetEdge(_make_repos(InMemoryEdgeRepository()))

    with pytest.raises(EdgeNotFoundError):
        await use_case.handle(GetEdgeQuery(edge_id=uuid.uuid4()), SYSTEM_ACTOR)

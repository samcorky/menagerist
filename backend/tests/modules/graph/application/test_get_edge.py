import uuid

import pytest

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.application.get_edge import GetEdge, GetEdgeQuery
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import EdgeNotFoundError
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_get_edge_returns_existing_edge() -> None:
    """GetEdge returns the edge when it exists."""
    repository = InMemoryEdgeRepository()
    edge = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
    await repository.add(edge)
    use_case = GetEdge(repository)

    result = await use_case.handle(GetEdgeQuery(edge_id=edge.id), SYSTEM_ACTOR)

    assert result is edge


async def test_get_edge_raises_when_missing() -> None:
    """GetEdge raises EdgeNotFoundError when the edge doesn't exist."""
    use_case = GetEdge(InMemoryEdgeRepository())

    with pytest.raises(EdgeNotFoundError):
        await use_case.handle(GetEdgeQuery(edge_id=uuid.uuid4()), SYSTEM_ACTOR)

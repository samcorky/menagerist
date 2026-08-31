import uuid

import pytest

from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.application.get_edge_type import GetEdgeType, GetEdgeTypeQuery
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_get_edge_type_returns_existing() -> None:
    """GetEdgeType returns the edge type when it exists."""
    repo = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repo.add(et)
    use_case = GetEdgeType(repo)

    result = await use_case.handle(GetEdgeTypeQuery(edge_type_id=et.id), SYSTEM_ACTOR)

    assert result is et


async def test_get_edge_type_raises_when_missing() -> None:
    """GetEdgeType raises EdgeTypeNotFoundError for an unknown id."""
    repo = InMemoryEdgeTypeRepository()
    use_case = GetEdgeType(repo)

    with pytest.raises(EdgeTypeNotFoundError):
        await use_case.handle(GetEdgeTypeQuery(edge_type_id=uuid.uuid4()), SYSTEM_ACTOR)

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
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.application.get_edge_type import GetEdgeType, GetEdgeTypeQuery
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_uow(edge_types: InMemoryEdgeTypeRepository) -> GraphUnitOfWork:
    return create_in_memory_graph_uow(
        GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=edge_types,
        )
    )


async def test_get_edge_type_returns_existing() -> None:
    """GetEdgeType returns the edge type when it exists."""
    edge_types = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await edge_types.add(et)
    use_case = GetEdgeType(_make_uow(edge_types))

    result = await use_case.handle(GetEdgeTypeQuery(edge_type_id=et.id), SYSTEM_ACTOR)

    assert result is et


async def test_get_edge_type_raises_when_missing() -> None:
    """GetEdgeType raises EdgeTypeNotFoundError for an unknown id."""
    use_case = GetEdgeType(_make_uow(InMemoryEdgeTypeRepository()))

    with pytest.raises(EdgeTypeNotFoundError):
        await use_case.handle(GetEdgeTypeQuery(edge_type_id=uuid.uuid4()), SYSTEM_ACTOR)

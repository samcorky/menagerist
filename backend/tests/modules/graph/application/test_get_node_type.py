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
from app.modules.graph.application.get_node_type import GetNodeType, GetNodeTypeQuery
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_uow(node_types: InMemoryNodeTypeRepository) -> GraphUnitOfWork:
    return create_in_memory_graph_uow(
        GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=node_types,
            edge_types=InMemoryEdgeTypeRepository(),
        )
    )


async def test_get_node_type_returns_existing() -> None:
    """GetNodeType returns the node type when it exists."""
    node_types = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")
    await node_types.add(nt)
    use_case = GetNodeType(_make_uow(node_types))

    result = await use_case.handle(GetNodeTypeQuery(node_type_id=nt.id), SYSTEM_ACTOR)

    assert result is nt


async def test_get_node_type_raises_when_missing() -> None:
    """GetNodeType raises NodeTypeNotFoundError for an unknown id."""
    use_case = GetNodeType(_make_uow(InMemoryNodeTypeRepository()))

    with pytest.raises(NodeTypeNotFoundError):
        await use_case.handle(GetNodeTypeQuery(node_type_id=uuid.uuid4()), SYSTEM_ACTOR)

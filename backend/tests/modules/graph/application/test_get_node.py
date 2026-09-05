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
from app.modules.graph.application.get_node import GetNode, GetNodeQuery
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_uow(nodes: InMemoryNodeRepository) -> GraphUnitOfWork:
    return create_in_memory_graph_uow(
        GraphRepos(
            nodes=nodes,
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
    )


async def test_get_node_returns_existing_node() -> None:
    """GetNode returns the node when it exists."""
    nodes = InMemoryNodeRepository()
    node = Node.create(name="Alien", type="film")
    await nodes.add(node)
    use_case = GetNode(_make_uow(nodes))

    result = await use_case.handle(GetNodeQuery(node_id=node.id), SYSTEM_ACTOR)

    assert result is node


async def test_get_node_raises_when_missing() -> None:
    """GetNode raises NodeNotFoundError when the node doesn't exist."""
    use_case = GetNode(_make_uow(InMemoryNodeRepository()))

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(GetNodeQuery(node_id=uuid.uuid4()), SYSTEM_ACTOR)

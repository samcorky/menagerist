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
from app.modules.graph.application.delete_node import DeleteNode, DeleteNodeCommand
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_delete_node_soft_deletes_and_commits() -> None:
    """DeleteNode soft-deletes the node and commits the unit of work."""
    repository = InMemoryNodeRepository()
    node = Node.create(name="Alien", type="film")
    await repository.add(node)
    repos = GraphRepos(
        nodes=repository,
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = create_in_memory_graph_uow(repos)
    use_case = DeleteNode(uow)

    await use_case.handle(DeleteNodeCommand(node_id=node.id), SYSTEM_ACTOR)

    assert await repos.nodes.get(node.id) is None


async def test_delete_node_raises_when_missing() -> None:
    """DeleteNode raises NodeNotFoundError when the node doesn't exist."""
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = create_in_memory_graph_uow(repos)
    use_case = DeleteNode(uow)

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(DeleteNodeCommand(node_id=uuid.uuid4()), SYSTEM_ACTOR)

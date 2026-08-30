import uuid

import pytest

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
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
from app.modules.graph.application.delete_edge import DeleteEdge, DeleteEdgeCommand
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import EdgeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_delete_edge_soft_deletes_and_commits() -> None:
    """DeleteEdge soft-deletes the edge and commits the unit of work."""
    repository = InMemoryEdgeRepository()
    edge = Edge.create(source_id=uuid.uuid4(), target_id=uuid.uuid4(), type="owns")
    await repository.add(edge)
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=repository,
        node_types=InMemoryNodeTypeRepository(),
    )
    uow = create_in_memory_graph_uow(repos)
    use_case = DeleteEdge(uow)

    await use_case.handle(DeleteEdgeCommand(edge_id=edge.id), SYSTEM_ACTOR)

    assert await repos.edges.get(edge.id) is None


async def test_delete_edge_raises_when_missing() -> None:
    """DeleteEdge raises EdgeNotFoundError when the edge doesn't exist."""
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
    )
    uow = create_in_memory_graph_uow(repos)
    use_case = DeleteEdge(uow)

    with pytest.raises(EdgeNotFoundError):
        await use_case.handle(DeleteEdgeCommand(edge_id=uuid.uuid4()), SYSTEM_ACTOR)

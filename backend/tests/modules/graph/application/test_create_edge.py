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
from app.modules.graph.application.create_edge import CreateEdge, CreateEdgeCommand
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


async def _repos_with_two_nodes() -> tuple[GraphRepos, Node, Node]:
    node_repo = InMemoryNodeRepository()
    source = Node.create(name="Alien", type="film")
    target = Node.create(name="Ridley Scott", type="person")
    await node_repo.add(source)
    await node_repo.add(target)
    return (
        GraphRepos(
            nodes=node_repo,
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        ),
        source,
        target,
    )


async def test_create_edge_persists_and_commits() -> None:
    """CreateEdge adds the edge to the repository and commits the unit of work."""
    repos, source, target = await _repos_with_two_nodes()
    uow = create_in_memory_graph_uow(repos)
    use_case = CreateEdge(uow)

    edge = await use_case.handle(
        CreateEdgeCommand(source_id=source.id, target_id=target.id, type="directed-by"),
        SYSTEM_ACTOR,
    )

    assert await repos.edges.get(edge.id) is edge
    assert uow.committed is True


async def test_create_edge_raises_when_source_missing() -> None:
    """CreateEdge raises NodeNotFoundError when the source node doesn't exist."""
    repos, _source, target = await _repos_with_two_nodes()
    uow = create_in_memory_graph_uow(repos)
    use_case = CreateEdge(uow)

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(
            CreateEdgeCommand(
                source_id=uuid.uuid4(), target_id=target.id, type="directed-by"
            ),
            SYSTEM_ACTOR,
        )


async def test_create_edge_raises_when_target_missing() -> None:
    """CreateEdge raises NodeNotFoundError when the target node doesn't exist."""
    repos, source, _target = await _repos_with_two_nodes()
    uow = create_in_memory_graph_uow(repos)
    use_case = CreateEdge(uow)

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(
            CreateEdgeCommand(
                source_id=source.id, target_id=uuid.uuid4(), type="directed-by"
            ),
            SYSTEM_ACTOR,
        )

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
from app.modules.graph.application.update_node import UpdateNode, UpdateNodeCommand
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_update_node_persists_and_commits() -> None:
    """UpdateNode saves the changed node and commits the unit of work."""
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
    use_case = UpdateNode(uow)

    result = await use_case.handle(
        UpdateNodeCommand(node_id=node.id, name="Alien (1979)"),
        SYSTEM_ACTOR,
    )

    assert result.name == "Alien (1979)"
    stored = await repos.nodes.get(node.id)
    assert stored is not None
    assert stored.name == "Alien (1979)"
    assert uow.committed is True


async def test_update_node_raises_when_missing() -> None:
    """UpdateNode raises NodeNotFoundError when the node doesn't exist."""
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = create_in_memory_graph_uow(repos)
    use_case = UpdateNode(uow)

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(
            UpdateNodeCommand(node_id=uuid.uuid4(), name="Alien"), SYSTEM_ACTOR
        )


async def test_update_node_skips_node_type_creation_when_type_exists() -> None:
    """UpdateNode does not duplicate NodeType when the slug already exists."""
    from app.modules.graph.domain.node_type import NodeType

    node_types = InMemoryNodeTypeRepository()
    existing = NodeType.create(slug="film", label="Film")
    await node_types.add(existing)

    repository = InMemoryNodeRepository()
    node = Node.create(name="Alien")
    await repository.add(node)
    repos = GraphRepos(
        nodes=repository,
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = create_in_memory_graph_uow(repos)
    use_case = UpdateNode(uow)

    await use_case.handle(
        UpdateNodeCommand(node_id=node.id, type="Film"),
        SYSTEM_ACTOR,
    )

    assert len(node_types._node_types) == 1


async def test_update_node_creates_node_type_when_type_is_new() -> None:
    """UpdateNode auto-creates a NodeType when the type slug doesn't exist yet."""
    node_types = InMemoryNodeTypeRepository()
    repository = InMemoryNodeRepository()
    node = Node.create(name="Alien")
    await repository.add(node)
    repos = GraphRepos(
        nodes=repository,
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = create_in_memory_graph_uow(repos)
    use_case = UpdateNode(uow)

    await use_case.handle(
        UpdateNodeCommand(node_id=node.id, type="Film"),
        SYSTEM_ACTOR,
    )

    film_type = await node_types.get_by_slug("film")
    assert film_type is not None
    assert film_type.label == "Film"

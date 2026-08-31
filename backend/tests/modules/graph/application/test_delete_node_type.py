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
from app.modules.graph.application.delete_node_type import (
    DeleteNodeType,
    DeleteNodeTypeCommand,
)
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos, GraphUnitOfWork
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_uow() -> tuple[GraphUnitOfWork, GraphRepos]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    return create_in_memory_graph_uow(repos), repos


async def test_delete_node_type_soft_deletes_and_commits() -> None:
    """DeleteNodeType marks the node type as deleted and commits."""
    uow, repos = _make_uow()
    nt = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(nt)
    use_case = DeleteNodeType(uow)

    await use_case.handle(DeleteNodeTypeCommand(node_type_id=nt.id), SYSTEM_ACTOR)

    assert nt.is_deleted is True
    assert uow.committed is True


async def test_delete_node_type_raises_when_missing() -> None:
    """DeleteNodeType raises NodeTypeNotFoundError when the node type doesn't exist."""
    uow, _ = _make_uow()
    use_case = DeleteNodeType(uow)

    with pytest.raises(NodeTypeNotFoundError):
        await use_case.handle(
            DeleteNodeTypeCommand(node_type_id=uuid.uuid4()), SYSTEM_ACTOR
        )

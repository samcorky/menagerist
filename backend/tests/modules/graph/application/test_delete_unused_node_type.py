import uuid
from unittest.mock import AsyncMock

import pytest

from app.entrypoints.api.shared.authorization import RoleAuthorizationAdapter
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
from app.modules.graph.application.delete_unused_node_type import (
    DeleteUnusedNodeType,
    DeleteUnusedNodeTypeCommand,
)
from app.modules.graph.domain.errors import NodeTypeInUseError, NodeTypeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

MEMBER = Actor(id=uuid.UUID(int=5), roles=frozenset({"member"}))


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


def _use_case(
    repos: GraphRepos,
) -> tuple[DeleteUnusedNodeType, InMemoryUnitOfWork[GraphRepos]]:
    uow = InMemoryUnitOfWork(repos)
    return DeleteUnusedNodeType(uow, RoleAuthorizationAdapter()), uow


async def test_an_unused_type_is_soft_deleted() -> None:
    """With no items the type is deleted and committed."""
    repos = _repos()
    node_type = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(node_type)
    use_case, uow = _use_case(repos)

    await use_case.handle(
        DeleteUnusedNodeTypeCommand(node_type_id=node_type.id), SYSTEM_ACTOR
    )

    assert node_type.is_deleted
    assert uow.committed is True


async def test_a_type_with_someone_elses_item_is_kept_and_nothing_is_written() -> None:
    """Any person's item blocks the delete; no write happens (no rollback here)."""
    repos = _repos()
    node_type = NodeType.create(slug="film", label="Film")
    await repos.node_types.add(node_type)
    item = Node.create(owner_id=uuid.UUID(int=9), name="Heat", type="film")
    await repos.nodes.add(item)
    repos.node_types.save = AsyncMock()  # type: ignore[method-assign]
    repos.nodes.clear_type = AsyncMock()  # type: ignore[method-assign]
    use_case, uow = _use_case(repos)

    with pytest.raises(NodeTypeInUseError):
        await use_case.handle(
            DeleteUnusedNodeTypeCommand(node_type_id=node_type.id), SYSTEM_ACTOR
        )

    assert not node_type.is_deleted
    assert item.type == "film"
    repos.node_types.save.assert_not_called()
    repos.nodes.clear_type.assert_not_called()
    assert uow.committed is False


async def test_a_missing_type_is_not_found() -> None:
    """An unknown id raises the not-found error."""
    use_case, _ = _use_case(_repos())

    with pytest.raises(NodeTypeNotFoundError):
        await use_case.handle(
            DeleteUnusedNodeTypeCommand(node_type_id=uuid.uuid4()), SYSTEM_ACTOR
        )


async def test_a_member_cannot_delete_a_type() -> None:
    """The delete needs the node type delete permission."""
    use_case, _ = _use_case(_repos())

    with pytest.raises(ForbiddenError):
        await use_case.handle(
            DeleteUnusedNodeTypeCommand(node_type_id=uuid.uuid4()), MEMBER
        )

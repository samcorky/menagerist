import uuid

import pytest

from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.get_node_type import GetNodeType, GetNodeTypeQuery
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_get_node_type_returns_existing() -> None:
    """GetNodeType returns the node type when it exists."""
    repo = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")
    await repo.add(nt)
    use_case = GetNodeType(repo)

    result = await use_case.handle(GetNodeTypeQuery(node_type_id=nt.id), SYSTEM_ACTOR)

    assert result is nt


async def test_get_node_type_raises_when_missing() -> None:
    """GetNodeType raises NodeTypeNotFoundError for an unknown id."""
    repo = InMemoryNodeTypeRepository()
    use_case = GetNodeType(repo)

    with pytest.raises(NodeTypeNotFoundError):
        await use_case.handle(GetNodeTypeQuery(node_type_id=uuid.uuid4()), SYSTEM_ACTOR)

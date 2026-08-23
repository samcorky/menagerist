import uuid

import pytest

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.application.get_node import GetNode, GetNodeQuery
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_get_node_returns_existing_node() -> None:
    """GetNode returns the node when it exists."""
    repository = InMemoryNodeRepository()
    node = Node.create(name="Alien", type="film")
    await repository.add(node)
    use_case = GetNode(repository)

    result = await use_case.handle(GetNodeQuery(node_id=node.id), SYSTEM_ACTOR)

    assert result is node


async def test_get_node_raises_when_missing() -> None:
    """GetNode raises NodeNotFoundError when the node doesn't exist."""
    use_case = GetNode(InMemoryNodeRepository())

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(GetNodeQuery(node_id=uuid.uuid4()), SYSTEM_ACTOR)

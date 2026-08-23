import uuid

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.domain.node import Node


async def test_add_and_get_round_trips() -> None:
    """A node added to the repository can be retrieved by id."""
    repository = InMemoryNodeRepository()
    node = Node.create(name="Alien", type="film")

    await repository.add(node)

    assert await repository.get(node.id) is node


async def test_get_returns_none_for_missing_node() -> None:
    """get() returns None for an id that was never added."""
    repository = InMemoryNodeRepository()

    assert await repository.get(uuid.uuid4()) is None


async def test_list_orders_by_id_ascending() -> None:
    """list() returns nodes ordered by id ascending, regardless of insert order."""
    repository = InMemoryNodeRepository()
    nodes = [Node.create(name="Alien", type="film") for _ in range(3)]
    for node in reversed(nodes):
        await repository.add(node)

    result = await repository.list(after=None, limit=10)

    assert result == sorted(nodes, key=lambda node: node.id)


async def test_list_respects_after_and_limit() -> None:
    """list() paginates using after/limit."""
    repository = InMemoryNodeRepository()
    nodes = sorted(
        (Node.create(name="Alien", type="film") for _ in range(4)), key=lambda n: n.id
    )
    for node in nodes:
        await repository.add(node)

    page = await repository.list(after=nodes[0].id, limit=2)

    assert page == nodes[1:3]

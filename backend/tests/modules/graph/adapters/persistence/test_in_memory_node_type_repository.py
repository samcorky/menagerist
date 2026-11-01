import uuid

from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.domain.node_type import NodeType


async def test_add_and_get_round_trips() -> None:
    """A node type added to the repository can be retrieved by id."""
    repo = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")

    await repo.add(nt)

    assert await repo.get(nt.id) is nt


async def test_get_returns_none_for_missing_id() -> None:
    """get() returns None for an id that was never added."""
    repo = InMemoryNodeTypeRepository()

    assert await repo.get(uuid.uuid4()) is None


async def test_get_by_slug_returns_matching_node_type() -> None:
    """get_by_slug() returns the node type with the matching slug."""
    repo = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")
    await repo.add(nt)

    assert await repo.get_by_slug("film") is nt


async def test_get_by_slug_returns_none_for_unknown_slug() -> None:
    """get_by_slug() returns None when the slug doesn't match anything."""
    repo = InMemoryNodeTypeRepository()

    assert await repo.get_by_slug("unknown") is None


async def test_list_orders_by_id_ascending() -> None:
    """list() returns node types ordered by id ascending."""
    repo = InMemoryNodeTypeRepository()
    types = [NodeType.create(slug=f"type-{i}", label=f"Type {i}") for i in range(3)]
    for nt in reversed(types):
        await repo.add(nt)

    result = await repo.list(after=None, limit=10)

    assert result == sorted(types, key=lambda t: t.id)


async def test_list_respects_after_and_limit() -> None:
    """list() paginates using after/limit."""
    repo = InMemoryNodeTypeRepository()
    types = sorted(
        (NodeType.create(slug=f"type-{i}", label=f"Type {i}") for i in range(4)),
        key=lambda t: t.id,
    )
    for nt in types:
        await repo.add(nt)

    page = await repo.list(after=types[0].id, limit=2)

    assert page == types[1:3]


async def test_save_persists_changes() -> None:
    """save() overwrites the stored node type."""
    repo = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")
    await repo.add(nt)

    nt.label = "Movie"
    await repo.save(nt)

    result = await repo.get(nt.id)
    assert result is not None
    assert result.label == "Movie"


async def test_get_returns_none_for_soft_deleted() -> None:
    """get() treats a soft-deleted node type as if it doesn't exist."""
    repo = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")
    await repo.add(nt)

    nt.soft_delete()
    await repo.save(nt)

    assert await repo.get(nt.id) is None


async def test_list_excludes_soft_deleted() -> None:
    """list() omits soft-deleted node types."""
    repo = InMemoryNodeTypeRepository()
    kept = NodeType.create(slug="film", label="Film")
    deleted = NodeType.create(slug="book", label="Book")
    await repo.add(kept)
    await repo.add(deleted)

    deleted.soft_delete()
    await repo.save(deleted)

    result = await repo.list(after=None, limit=10)

    assert result == [kept]


async def test_get_by_slug_returns_none_for_soft_deleted() -> None:
    """get_by_slug() does not return soft-deleted node types."""
    repo = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")
    await repo.add(nt)
    nt.soft_delete()
    await repo.save(nt)

    assert await repo.get_by_slug("film") is None

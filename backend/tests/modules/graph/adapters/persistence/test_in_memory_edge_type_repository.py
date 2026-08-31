import uuid

from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.domain.edge_type import EdgeType


async def test_add_and_get_round_trips() -> None:
    """An edge type added to the repository can be retrieved by id."""
    repo = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="directed-by", label="Directed By")

    await repo.add(et)

    assert await repo.get(et.id) is et


async def test_get_returns_none_for_missing_id() -> None:
    """get() returns None for an id that was never added."""
    repo = InMemoryEdgeTypeRepository()

    assert await repo.get(uuid.uuid4()) is None


async def test_get_by_slug_returns_matching_edge_type() -> None:
    """get_by_slug() returns the edge type with the matching slug."""
    repo = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repo.add(et)

    assert await repo.get_by_slug("directed-by") is et


async def test_get_by_slug_returns_none_for_unknown_slug() -> None:
    """get_by_slug() returns None when the slug doesn't match anything."""
    repo = InMemoryEdgeTypeRepository()

    assert await repo.get_by_slug("unknown") is None


async def test_list_orders_by_id_ascending() -> None:
    """list() returns edge types ordered by id ascending."""
    repo = InMemoryEdgeTypeRepository()
    types = [EdgeType.create(slug=f"type-{i}", label=f"Type {i}") for i in range(3)]
    for et in reversed(types):
        await repo.add(et)

    result = await repo.list(after=None, limit=10)

    assert result == sorted(types, key=lambda t: t.id)


async def test_list_respects_after_and_limit() -> None:
    """list() paginates using after/limit."""
    repo = InMemoryEdgeTypeRepository()
    types = sorted(
        (EdgeType.create(slug=f"type-{i}", label=f"Type {i}") for i in range(4)),
        key=lambda t: t.id,
    )
    for et in types:
        await repo.add(et)

    page = await repo.list(after=types[0].id, limit=2)

    assert page == types[1:3]


async def test_save_persists_changes() -> None:
    """save() overwrites the stored edge type."""
    repo = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repo.add(et)

    et.label = "Helmed By"
    await repo.save(et)

    result = await repo.get(et.id)
    assert result is not None
    assert result.label == "Helmed By"


async def test_get_returns_none_for_soft_deleted() -> None:
    """get() treats a soft-deleted edge type as if it doesn't exist."""
    repo = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repo.add(et)

    et.soft_delete()
    await repo.save(et)

    assert await repo.get(et.id) is None


async def test_list_excludes_soft_deleted() -> None:
    """list() omits soft-deleted edge types."""
    repo = InMemoryEdgeTypeRepository()
    kept = EdgeType.create(slug="directed-by", label="Directed By")
    deleted = EdgeType.create(slug="written-by", label="Written By")
    await repo.add(kept)
    await repo.add(deleted)

    deleted.soft_delete()
    await repo.save(deleted)

    result = await repo.list(after=None, limit=10)

    assert result == [kept]


async def test_get_by_slug_returns_none_for_soft_deleted() -> None:
    """get_by_slug() does not return soft-deleted edge types."""
    repo = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="directed-by", label="Directed By")
    await repo.add(et)
    et.soft_delete()
    await repo.save(et)

    assert await repo.get_by_slug("directed-by") is None

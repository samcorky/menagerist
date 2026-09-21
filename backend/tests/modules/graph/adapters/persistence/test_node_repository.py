import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.node import Node

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


def _fields(node: Node) -> tuple[object, ...]:
    return (
        node.id,
        node.name,
        node.type,
        node.description,
        node.attributes,
        node.favourite,
        node.tags,
        node.created_at,
        node.updated_at,
        node.deleted_at,
    )


async def test_add_and_get_round_trips(db_session: AsyncSession) -> None:
    """A node added to the repository can be retrieved by id."""
    repository = SqlAlchemyNodeRepository(db_session)
    node = Node.create(name="Alien", type="film")

    await repository.add(node)
    result = await repository.get(node.id)

    assert result is not None
    assert _fields(result) == _fields(node)


async def test_get_returns_none_for_missing_node(db_session: AsyncSession) -> None:
    """get() returns None for an id that was never added."""
    repository = SqlAlchemyNodeRepository(db_session)

    assert await repository.get(uuid.uuid4()) is None


async def test_list_orders_by_id_ascending(db_session: AsyncSession) -> None:
    """list() returns node ordered by id ascending, regardless of insert order."""
    repository = SqlAlchemyNodeRepository(db_session)
    nodes = [Node.create(name="Alien", type="film") for _ in range(3)]
    for node in reversed(nodes):
        await repository.add(node)

    result = await repository.list(after=None, limit=10)

    assert [n.id for n in result] == sorted(n.id for n in nodes)


async def test_list_respects_after_and_limit(db_session: AsyncSession) -> None:
    """list() paginates using after/limit."""
    repository = SqlAlchemyNodeRepository(db_session)
    nodes = sorted(
        (Node.create(name="Alien", type="film") for _ in range(4)), key=lambda n: n.id
    )
    for node in nodes:
        await repository.add(node)

    page = await repository.list(after=nodes[0].id, limit=2)

    assert [n.id for n in page] == [n.id for n in nodes[1:3]]


async def test_save_persists_changes_to_an_existing_node(
    db_session: AsyncSession,
) -> None:
    """save() overwrites the stored node with the given instance."""
    repository = SqlAlchemyNodeRepository(db_session)
    node = Node.create(name="Alien", type="film")
    await repository.add(node)

    node.update(name="Alien (1979)")
    await repository.save(node)

    result = await repository.get(node.id)
    assert result is not None
    assert result.name == "Alien (1979)"


async def test_get_returns_none_for_a_soft_deleted_node(
    db_session: AsyncSession,
) -> None:
    """get() treats a soft-deleted node as if it doesn't exist."""
    repository = SqlAlchemyNodeRepository(db_session)
    node = Node.create(name="Alien", type="film")
    await repository.add(node)

    node.soft_delete()
    await repository.save(node)

    assert await repository.get(node.id) is None


async def test_favourite_field_round_trips(db_session: AsyncSession) -> None:
    """A node created with favourite=True stores and retrieves the value correctly."""
    repository = SqlAlchemyNodeRepository(db_session)
    node = Node.create(name="Alien", favourite=True)

    await repository.add(node)
    result = await repository.get(node.id)

    assert result is not None
    assert result.favourite is True
    assert _fields(result) == _fields(node)


async def test_save_persists_favourite_change(db_session: AsyncSession) -> None:
    """save() persists a change to the favourite field."""
    repository = SqlAlchemyNodeRepository(db_session)
    node = Node.create(name="Alien")
    await repository.add(node)

    node.update(favourite=True)
    await repository.save(node)

    result = await repository.get(node.id)
    assert result is not None
    assert result.favourite is True


async def test_list_filters_by_favourite(db_session: AsyncSession) -> None:
    """list(favourite=True) returns only favourited nodes."""
    repository = SqlAlchemyNodeRepository(db_session)
    starred = Node.create(name="Alien", favourite=True)
    plain = Node.create(name="Predator")
    await repository.add(starred)
    await repository.add(plain)

    result = await repository.list(after=None, limit=10, favourite=True)

    assert [n.id for n in result] == [starred.id]


async def test_count_filters_by_favourite(db_session: AsyncSession) -> None:
    """count(favourite=True) counts only favourited nodes."""
    repository = SqlAlchemyNodeRepository(db_session)
    for _ in range(3):
        await repository.add(Node.create(name="Alien", favourite=True))
    for _ in range(2):
        await repository.add(Node.create(name="Predator"))

    assert await repository.count(favourite=True) == 3
    assert await repository.count(favourite=False) == 2


async def test_list_excludes_soft_deleted_nodes(db_session: AsyncSession) -> None:
    """list() omits soft-deleted node."""
    repository = SqlAlchemyNodeRepository(db_session)
    kept = Node.create(name="Alien", type="film")
    deleted = Node.create(name="Predator", type="film")
    await repository.add(kept)
    await repository.add(deleted)

    deleted.soft_delete()
    await repository.save(deleted)

    result = await repository.list(after=None, limit=10)

    assert [n.id for n in result] == [kept.id]


async def test_tags_round_trip(db_session: AsyncSession) -> None:
    """Tags are stored as JSONB and come back as the same list, and updates persist."""
    repository = SqlAlchemyNodeRepository(db_session)
    node = Node.create(name="Alien", tags=["Sci-Fi", "horror"])
    await repository.add(node)

    result = await repository.get(node.id)

    assert result is not None
    assert result.tags == ["sci-fi", "horror"]

    node.update(tags=["classic"])
    await repository.save(node)
    updated = await repository.get(node.id)

    assert updated is not None
    assert updated.tags == ["classic"]


async def test_count_and_list_with_attribute_use_jsonb_key_lookup(
    db_session: AsyncSession,
) -> None:
    """Only live nodes of the type whose JSONB attributes hold the key match."""
    repository = SqlAlchemyNodeRepository(db_session)
    nodes = [
        Node.create(name=f"n{i}", type="film", attributes={"k": i, "keep": 1})
        for i in range(3)
    ]
    gone = Node.create(name="gone", type="film", attributes={"k": 9})
    gone.soft_delete()
    for node in [
        *nodes,
        Node.create(name="book", type="book", attributes={"k": 1}),
        Node.create(name="bare", type="film", attributes={"keep": 1}),
        Node.create(name="null", type="film", attributes={"k": None}),
        gone,
    ]:
        await repository.add(node)

    assert await repository.count_with_attribute("film", "k") == 4
    page = await repository.list_with_attribute("film", "k", after=None, limit=2)
    assert len(page) == 2
    rest = await repository.list_with_attribute(
        "film", "k", after=page[-1].id, limit=10
    )
    assert len(rest) == 2
    assert {n.name for n in [*page, *rest]} == {"n0", "n1", "n2", "null"}
    assert await repository.count_with_attribute("film", "missing") == 0


async def test_count_with_attribute_matches_an_exact_string_value(
    db_session: AsyncSession,
) -> None:
    """With `value`, JSONB containment counts only exact matches on that key."""
    repository = SqlAlchemyNodeRepository(db_session)
    cases: list[tuple[str, dict[str, object]]] = [
        ("a", {"s": "Draft"}),
        ("b", {"s": "Draft", "x": 1}),
        ("c", {"s": "Live"}),
        ("d", {"s": 1}),
        ("e", {"x": "Draft"}),
    ]
    for name, attrs in cases:
        await repository.add(Node.create(name=name, type="film", attributes=attrs))

    assert await repository.count_with_attribute("film", "s", value="Draft") == 2
    assert await repository.count_with_attribute("film", "s", value="1") == 0
    assert await repository.count_with_attribute("film", "s") == 4

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
    """list() returns nodes ordered by id ascending, regardless of insert order."""
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


async def test_list_excludes_soft_deleted_nodes(db_session: AsyncSession) -> None:
    """list() omits soft-deleted nodes."""
    repository = SqlAlchemyNodeRepository(db_session)
    kept = Node.create(name="Alien", type="film")
    deleted = Node.create(name="Predator", type="film")
    await repository.add(kept)
    await repository.add(deleted)

    deleted.soft_delete()
    await repository.save(deleted)

    result = await repository.list(after=None, limit=10)

    assert [n.id for n in result] == [kept.id]

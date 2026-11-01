"""`NodeRepository.count_by_type`, against the in-memory and Postgres adapters."""

import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import TypeCount
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
A = ContentFilter.of(ALICE)
B = ContentFilter.of(BOB)
ALL = ContentFilter.everyone()


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repository(request: pytest.FixtureRequest) -> NodeRepository:
    """The same scenarios run against both adapters."""
    if request.param == "in_memory":
        return InMemoryNodeRepository()
    return SqlAlchemyNodeRepository(request.getfixturevalue("db_session"))


async def _add(
    repository: NodeRepository,
    type_slug: str | None,
    *,
    owner: uuid.UUID = ALICE,
    deleted: bool = False,
) -> Node:
    node = Node.create(owner_id=owner, name="n", type=type_slug)
    if deleted:
        node.soft_delete()
    await repository.add(node)
    return node


async def test_empty_store_counts_nothing(repository: NodeRepository) -> None:
    """Empty store counts nothing."""
    assert await repository.count_by_type(scope=ALL) == []


async def test_counts_each_type_biggest_first_then_by_slug(
    repository: NodeRepository,
) -> None:
    """Counts each type biggest first, then by slug."""
    for slug in ("film", "film", "film", "book", "record", "record"):
        await _add(repository, slug)
    await _add(repository, "album")

    assert await repository.count_by_type(scope=A) == [
        TypeCount(type="film", count=3),
        TypeCount(type="record", count=2),
        TypeCount(type="album", count=1),
        TypeCount(type="book", count=1),
    ]


async def test_untyped_items_are_one_row_with_no_type_listed_last_on_a_tie(
    repository: NodeRepository,
) -> None:
    """Untyped items are one row with no type, after the types on a tie."""
    await _add(repository, None)
    await _add(repository, "film")
    await _add(repository, "book")

    assert await repository.count_by_type(scope=A) == [
        TypeCount(type="book", count=1),
        TypeCount(type="film", count=1),
        TypeCount(type=None, count=1),
    ]


async def test_an_untyped_row_still_sorts_by_count_among_the_rest(
    repository: NodeRepository,
) -> None:
    """Counts decide the order; only ties put the untyped row after the types."""
    for _ in range(3):
        await _add(repository, None)
    await _add(repository, "film")

    assert await repository.count_by_type(scope=A) == [
        TypeCount(type=None, count=3),
        TypeCount(type="film", count=1),
    ]


async def test_ignores_deleted_items(repository: NodeRepository) -> None:
    """Ignores deleted items."""
    await _add(repository, "film")
    await _add(repository, "film", deleted=True)
    await _add(repository, "book", deleted=True)

    assert await repository.count_by_type(scope=A) == [TypeCount(type="film", count=1)]


async def test_counts_only_the_scope_owner_unless_everyone(
    repository: NodeRepository,
) -> None:
    """Counts only the scope owner unless everyone."""
    await _add(repository, "film", owner=ALICE)
    await _add(repository, "film", owner=BOB)
    await _add(repository, "book", owner=BOB)

    assert await repository.count_by_type(scope=A) == [TypeCount(type="film", count=1)]
    assert await repository.count_by_type(scope=B) == [
        TypeCount(type="book", count=1),
        TypeCount(type="film", count=1),
    ]
    assert await repository.count_by_type(scope=ALL) == [
        TypeCount(type="film", count=2),
        TypeCount(type="book", count=1),
    ]

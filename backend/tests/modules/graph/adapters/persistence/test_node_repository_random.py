"""`NodeRepository.random`, against the in-memory and Postgres adapters."""

import uuid
from datetime import date
from typing import TYPE_CHECKING

import pytest

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import Group, Query, ResolvedQuery, TypeCondition
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
A = ContentFilter.of(ALICE)
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
    name: str = "n",
    *,
    type_slug: str | None = "film",
    owner: uuid.UUID = ALICE,
    favourite: bool = False,
    deleted: bool = False,
) -> Node:
    node = Node.create(owner_id=owner, name=name, type=type_slug, favourite=favourite)
    if deleted:
        node.soft_delete()
    await repository.add(node)
    return node


def _films_only() -> ResolvedQuery:
    where = Group(op="and", children=(TypeCondition(slugs=("film",)),))
    return ResolvedQuery(
        query=Query(where=where),
        field_kinds={},
        search_exclusions={},
        today=date(2026, 10, 29),
    )


async def test_an_empty_store_has_nothing_to_pick(repository: NodeRepository) -> None:
    """Nothing stored, nothing picked."""
    assert await repository.random(scope=ALL) is None


async def test_picks_the_only_live_item_in_scope(repository: NodeRepository) -> None:
    """Deleted items and other people's items are never picked."""
    mine = await _add(repository, "mine")
    await _add(repository, "gone", deleted=True)
    await _add(repository, "theirs", owner=BOB)

    picked = await repository.random(scope=A)

    assert picked is not None
    assert picked.id == mine.id


async def test_every_matching_item_can_be_picked(repository: NodeRepository) -> None:
    """Repeated picks reach each of the items, so it is not stuck on one."""
    ids = {(await _add(repository, f"item {i}")).id for i in range(3)}
    seen: set[uuid.UUID] = set()
    for _ in range(200):
        picked = await repository.random(scope=A)
        assert picked is not None
        seen.add(picked.id)
        if seen == ids:
            break
    assert seen == ids


async def test_filters_by_type_and_favourite(repository: NodeRepository) -> None:
    """Only items with the given type, or favourite state, are picked."""
    book = await _add(repository, "book", type_slug="book")
    fav = await _add(repository, "fav", favourite=True)
    await _add(repository, "plain")

    picked_book = await repository.random(scope=A, type="book")
    picked_fav = await repository.random(scope=A, favourite=True)

    assert picked_book is not None
    assert picked_book.id == book.id
    assert picked_fav is not None
    assert picked_fav.id == fav.id
    assert await repository.random(scope=A, type="record") is None


async def test_restricts_to_the_given_ids(repository: NodeRepository) -> None:
    """With ids, only those items are picked; an empty set picks nothing."""
    inside = await _add(repository, "inside")
    await _add(repository, "outside")

    picked = await repository.random(scope=A, ids={inside.id})

    assert picked is not None
    assert picked.id == inside.id
    assert await repository.random(scope=A, ids=set()) is None


async def test_picks_from_a_resolved_query(repository: NodeRepository) -> None:
    """A resolved query (a smart collection) narrows the pick the way search does."""
    film = await _add(repository, "film")
    await _add(repository, "book", type_slug="book")

    picked = await repository.random(scope=A, resolved=_films_only())

    assert picked is not None
    assert picked.id == film.id

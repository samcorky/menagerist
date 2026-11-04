"""Favourites belong to one person and one item, in both node repositories."""

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
from app.modules.graph.domain.query import (
    FavouriteCondition,
    Group,
    Query,
    ResolvedQuery,
)
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=201)
BOB = uuid.UUID(int=202)
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
    repository: NodeRepository, owner: uuid.UUID, name: str, *, favourite: bool = False
) -> Node:
    node = Node.create(owner_id=owner, name=name, favourite=favourite)
    await repository.add(node)
    return node


def _favourites_query(*, value: bool) -> ResolvedQuery:
    return ResolvedQuery(
        query=Query(where=Group(op="and", children=(FavouriteCondition(value=value),))),
        field_kinds={},
        search_exclusions={},
        today=date(2026, 11, 4),
    )


async def test_a_new_node_is_not_a_favourite(repository: NodeRepository) -> None:
    """Nothing is a favourite until someone makes it one."""
    node = await _add(repository, ALICE, "Alien")

    fetched = await repository.get(node.id, scope=A)

    assert fetched is not None
    assert fetched.favourite is False


async def test_a_node_added_as_a_favourite_is_its_owners(
    repository: NodeRepository,
) -> None:
    """`favourite=True` at creation records the owner's favourite."""
    node = await _add(repository, ALICE, "Alien", favourite=True)

    fetched = await repository.get(node.id, scope=A)

    assert fetched is not None
    assert fetched.favourite is True


async def test_set_favourite_marks_and_clears_it_for_that_person(
    repository: NodeRepository,
) -> None:
    """Favouriting is a toggle, and repeating either direction is harmless."""
    node = await _add(repository, ALICE, "Alien")

    await repository.set_favourite(node.id, True, scope=A)
    await repository.set_favourite(node.id, True, scope=A)
    marked = await repository.get(node.id, scope=A)
    assert marked is not None
    was_marked = marked.favourite
    await repository.set_favourite(node.id, False, scope=A)
    await repository.set_favourite(node.id, False, scope=A)
    cleared = await repository.get(node.id, scope=A)

    assert was_marked is True
    assert cleared is not None
    assert cleared.favourite is False


async def test_set_favourite_leaves_the_node_itself_alone(
    repository: NodeRepository,
) -> None:
    """Starring does not edit the item, so its timestamp is unchanged."""
    node = await _add(repository, ALICE, "Alien")
    before = node.updated_at

    await repository.set_favourite(node.id, True, scope=A)

    fetched = await repository.get(node.id, scope=A)
    assert fetched is not None
    assert fetched.updated_at == before


async def test_one_person_cannot_favourite_another_persons_node(
    repository: NodeRepository,
) -> None:
    """A node outside the scope is not touched, and not revealed."""
    node = await _add(repository, ALICE, "Alien")

    await repository.set_favourite(node.id, True, scope=B)

    mine = await repository.get(node.id, scope=A)
    assert mine is not None
    assert mine.favourite is False
    assert await repository.get(node.id, scope=B) is None


async def test_favouriting_without_a_person_is_refused(
    repository: NodeRepository,
) -> None:
    """`everyone()` names nobody, so there is no one to favourite for."""
    node = await _add(repository, ALICE, "Alien")

    with pytest.raises(ValueError, match="one person"):
        await repository.set_favourite(node.id, True, scope=ALL)


async def test_the_system_scope_never_sees_a_favourite(
    repository: NodeRepository,
) -> None:
    """A favourite is someone's own, so a read with no person shows none."""
    node = await _add(repository, ALICE, "Alien", favourite=True)

    fetched = await repository.get(node.id, scope=ALL)

    assert fetched is not None
    assert fetched.favourite is False
    assert await repository.count(scope=ALL, favourite=True) == 0
    assert await repository.count(scope=ALL, favourite=False) == 1


async def test_filters_use_only_the_callers_favourites(
    repository: NodeRepository,
) -> None:
    """The plain list, count and random filters follow the scope's person."""
    alien = await _add(repository, ALICE, "Alien", favourite=True)
    await _add(repository, ALICE, "Aliens")
    await _add(repository, BOB, "Blade Runner", favourite=True)
    await _add(repository, BOB, "Brazil")

    alices = await repository.list(scope=A, after=None, limit=10, favourite=True)
    others = await repository.list(scope=A, after=None, limit=10, favourite=False)
    picked = await repository.random(scope=A, favourite=True)

    assert [n.id for n in alices] == [alien.id]
    assert [n.name for n in others] == ["Aliens"]
    assert await repository.count(scope=A, favourite=True) == 1
    assert await repository.count(scope=B, favourite=True) == 1
    assert picked is not None
    assert picked.id == alien.id


async def test_a_favourite_condition_follows_the_callers_favourites(
    repository: NodeRepository,
) -> None:
    """A saved search's `favourite` condition is judged for whoever runs it."""
    alien = await _add(repository, ALICE, "Alien", favourite=True)
    plain = await _add(repository, ALICE, "Aliens")
    await _add(repository, BOB, "Blade Runner", favourite=True)

    starred = await repository.search(
        scope=A, resolved=_favourites_query(value=True), after=None, limit=10
    )
    unstarred = await repository.search(
        scope=A, resolved=_favourites_query(value=False), after=None, limit=10
    )

    assert [hit.node.id for hit in starred] == [alien.id]
    assert [hit.node.favourite for hit in starred] == [True]
    assert [hit.node.id for hit in unstarred] == [plain.id]
    assert [hit.node.favourite for hit in unstarred] == [False]
    assert (
        await repository.search_count(scope=A, resolved=_favourites_query(value=True))
        == 1
    )


async def test_a_favourite_survives_deleting_and_restoring_the_node(
    repository: NodeRepository,
) -> None:
    """Recently deleted keeps the star, so a restored item is as it was."""
    node = await _add(repository, ALICE, "Alien", favourite=True)
    node.soft_delete()
    await repository.save(node)
    node.restore()
    await repository.save(node)

    fetched = await repository.get(node.id, scope=A)

    assert fetched is not None
    assert fetched.favourite is True


async def test_purging_a_node_removes_its_favourites(
    repository: NodeRepository,
) -> None:
    """A hard delete takes the favourites with it: nothing is left to resurface."""
    node = await _add(repository, ALICE, "Alien", favourite=True)
    await repository.purge(node.id)

    again = Node.create(owner_id=ALICE, name="Alien")
    again.id = node.id
    await repository.add(again)

    fetched = await repository.get(node.id, scope=A)
    assert fetched is not None
    assert fetched.favourite is False


async def test_saving_a_node_does_not_store_a_favourite(
    repository: NodeRepository,
) -> None:
    """`Node.favourite` is only what a read reports; saving never writes it."""
    node = await _add(repository, ALICE, "Alien")
    node.favourite = True
    node.name = "Alien (1979)"
    await repository.save(node)

    fetched = await repository.get(node.id, scope=A)

    assert fetched is not None
    assert fetched.name == "Alien (1979)"
    assert fetched.favourite is False

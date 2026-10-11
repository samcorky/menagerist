"""Every scoped `NodeRepository` method, against the in-memory and Postgres adapters."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.node import Node
from app.shared_kernel.access_scope import AccessScope

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=101)
BOB = uuid.UUID(int=102)
A = AccessScope.of(ALICE)
B = AccessScope.of(BOB)
ALL = AccessScope.everyone()


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repository(request: pytest.FixtureRequest) -> NodeRepository:
    """The same scenarios run against both adapters."""
    if request.param == "in_memory":
        return InMemoryNodeRepository()
    return SqlAlchemyNodeRepository(request.getfixturevalue("db_session"))


def _node(owner: uuid.UUID | None, name: str, **kwargs: Any) -> Node:  # noqa: ANN401
    node = Node.create(owner_id=ALICE, name=name, **kwargs)
    node.owner_id = owner
    return node


async def _add(repository: NodeRepository, *nodes: Node) -> None:
    for node in nodes:
        await repository.add(node)


async def test_get_hides_other_users_nodes(repository: NodeRepository) -> None:
    """A's node is visible to A and everyone(), never to B."""
    node = _node(ALICE, "Alien")
    await _add(repository, node)

    assert await repository.get(node.id, scope=A) is not None
    assert await repository.get(node.id, scope=ALL) is not None
    assert await repository.get(node.id, scope=B) is None


async def test_get_hides_soft_deleted_nodes(repository: NodeRepository) -> None:
    """A soft-deleted node is invisible even to its owner and everyone()."""
    node = _node(ALICE, "Alien")
    await _add(repository, node)
    node.soft_delete()
    await repository.save(node)

    assert await repository.get(node.id, scope=A) is None
    assert await repository.get(node.id, scope=ALL) is None


async def test_ownerless_nodes_are_visible_only_to_everyone(
    repository: NodeRepository,
) -> None:
    """A NULL-owner row belongs to nobody: only the all-scope sees it."""
    orphan = _node(None, "Orphan", type="film")
    await _add(repository, orphan)

    assert await repository.get(orphan.id, scope=A) is None
    assert await repository.get(orphan.id, scope=ALL) is not None
    assert await repository.list(scope=A, after=None, limit=10) == []
    assert [n.id for n in await repository.list(scope=ALL, after=None, limit=10)] == [
        orphan.id
    ]
    assert await repository.count(scope=A) == 0
    assert await repository.count(scope=ALL) == 1


async def test_list_and_count_are_scoped(repository: NodeRepository) -> None:
    """Each user lists only their own nodes and counts match the lists."""
    mine = [_node(ALICE, f"A{i}") for i in range(3)]
    theirs = [_node(BOB, f"B{i}") for i in range(2)]
    gone = _node(ALICE, "Gone")
    await _add(repository, *mine, *theirs, gone)
    gone.soft_delete()
    await repository.save(gone)

    a_ids = {n.id for n in await repository.list(scope=A, after=None, limit=50)}
    b_ids = {n.id for n in await repository.list(scope=B, after=None, limit=50)}
    all_ids = {n.id for n in await repository.list(scope=ALL, after=None, limit=50)}

    assert a_ids == {n.id for n in mine}
    assert b_ids == {n.id for n in theirs}
    assert all_ids == a_ids | b_ids
    assert await repository.count(scope=A) == 3
    assert await repository.count(scope=B) == 2
    assert await repository.count(scope=ALL) == 5


async def test_keyset_pagination_stays_inside_the_scope(
    repository: NodeRepository,
) -> None:
    """Paging through A's nodes never surfaces B's, whatever the interleaving."""
    nodes = [_node(ALICE if i % 2 == 0 else BOB, f"N{i}") for i in range(8)]
    await _add(repository, *nodes)

    seen: list[uuid.UUID] = []
    after: uuid.UUID | None = None
    while page := await repository.list(scope=A, after=after, limit=2):
        seen.extend(n.id for n in page)
        after = page[-1].id

    assert seen == sorted(n.id for n in nodes if n.owner_id == ALICE)


async def test_filters_combine_with_scope_and_counts_mirror_lists(
    repository: NodeRepository,
) -> None:
    """type, favourite and ids filters are ANDed with the scope; count == list."""
    a_film = _node(ALICE, "Alien", type="film", favourite=True)
    a_book = _node(ALICE, "Dune", type="book")
    b_film = _node(BOB, "Blade Runner", type="film", favourite=True)
    await _add(repository, a_film, a_book, b_film)
    everything = [a_film.id, a_book.id, b_film.id]

    cases: list[dict[str, Any]] = [
        {"type": "film"},
        {"favourite": True},
        {"ids": everything},
        {"ids": [b_film.id]},
        {"ids": []},
        {"type": "film", "favourite": True, "ids": everything},
    ]
    for filters in cases:
        for scope in (A, B, ALL):
            listed = await repository.list(scope=scope, after=None, limit=50, **filters)
            counted = await repository.count(scope=scope, **filters)
            assert counted == len(listed), (filters, scope)

    only_b = await repository.list(scope=A, after=None, limit=50, ids=[b_film.id])
    assert only_b == []
    assert await repository.count(scope=A, ids=[b_film.id]) == 0
    mine = await repository.list(scope=A, after=None, limit=50, type="film")
    assert [n.id for n in mine] == [a_film.id]


async def test_search_is_scoped_across_name_description_and_attributes(
    repository: NodeRepository,
) -> None:
    """`q` matches only the viewer's nodes, accent-insensitively."""
    a_name = _node(ALICE, "Cafe Society")
    a_desc = _node(ALICE, "Plain", description="a quiet café")
    a_attr = _node(ALICE, "Other", attributes={"venue": "Café Royal"})
    b_name = _node(BOB, "Café Noir")
    b_attr = _node(BOB, "More", attributes={"venue": "cafe bar"})
    await _add(repository, a_name, a_desc, a_attr, b_name, b_attr)

    mine = await repository.list(scope=A, after=None, limit=50, q="CAFE")
    theirs = await repository.list(scope=B, after=None, limit=50, q="café")

    assert {n.id for n in mine} == {a_name.id, a_desc.id, a_attr.id}
    assert {n.id for n in theirs} == {b_name.id, b_attr.id}
    assert await repository.count(scope=A, q="CAFE") == 3
    assert await repository.count(scope=B, q="café") == 2
    assert await repository.count(scope=ALL, q="cafe") == 5
    assert await repository.list(scope=A, after=None, limit=50, q="noir") == []


async def test_clear_type_only_touches_the_scope(repository: NodeRepository) -> None:
    """Clearing a type for A leaves B's nodes typed; everyone() clears all."""
    a_film = _node(ALICE, "Alien", type="film")
    b_film = _node(BOB, "Blade Runner", type="film")
    await _add(repository, a_film, b_film)

    await repository.clear_type("film", scope=A)

    a_after = await repository.get(a_film.id, scope=ALL)
    b_after = await repository.get(b_film.id, scope=ALL)
    assert a_after is not None
    assert a_after.type is None
    assert b_after is not None
    assert b_after.type == "film"

    await repository.clear_type("film", scope=ALL)
    b_cleared = await repository.get(b_film.id, scope=ALL)
    assert b_cleared is not None
    assert b_cleared.type is None


async def test_attribute_counts_and_lists_are_scoped(
    repository: NodeRepository,
) -> None:
    """Usage counts and attribute listings see only the viewer's nodes."""
    a_one = _node(ALICE, "One", type="film", attributes={"rating": "PG"})
    a_two = _node(ALICE, "Two", type="film", attributes={"rating": "PG"})
    b_one = _node(BOB, "Three", type="film", attributes={"rating": "R"})
    await _add(repository, a_one, a_two, b_one)

    assert await repository.count_with_attribute("film", "rating", scope=A) == 2
    assert await repository.count_with_attribute("film", "rating", scope=B) == 1
    assert await repository.count_with_attribute("film", "rating", scope=ALL) == 3
    assert (
        await repository.count_with_attribute("film", "rating", scope=A, value="R") == 0
    )

    listed = await repository.list_with_attribute(
        "film", "rating", scope=A, after=None, limit=50
    )
    assert {n.id for n in listed} == {a_one.id, a_two.id}
    b_listed = await repository.list_with_attribute(
        "film", "rating", scope=B, after=None, limit=50
    )
    assert [n.id for n in b_listed] == [b_one.id]

    assert await repository.list_attribute_values("film", "rating", scope=A) == [
        ("PG", 2)
    ]
    assert await repository.list_attribute_values("film", "rating", scope=B) == [
        ("R", 1)
    ]
    assert await repository.list_attribute_values("film", "rating", scope=ALL) == [
        ("PG", 2),
        ("R", 1),
    ]


async def test_group_attribute_counts_are_scoped(repository: NodeRepository) -> None:
    """Group (array-of-objects) usage respects the scope too."""
    rows = [{"role": "lead"}]
    a_node = _node(ALICE, "One", type="film", attributes={"cast": rows})
    b_node = _node(BOB, "Two", type="film", attributes={"cast": rows})
    await _add(repository, a_node, b_node)

    assert (
        await repository.count_with_attribute("film", "cast", scope=B, sub_key="role")
        == 1
    )
    listed = await repository.list_with_attribute(
        "film", "cast", scope=A, sub_key="role", after=None, limit=10
    )
    assert [n.id for n in listed] == [a_node.id]

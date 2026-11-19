import uuid

import pytest

from app.modules.graph.adapters.persistence.in_memory_collection_members import (
    InMemoryCollectionMembers,
)
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.count_node_types import (
    CountNodeTypes,
    CountNodeTypesQuery,
)
from app.modules.graph.application.list_nodes import ListNodes
from app.modules.graph.domain.errors import CollectionNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import TypeCount
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

ALICE = Actor(id=uuid.UUID(int=11), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=12), roles=frozenset({"member"}))


def _use_case(
    repos: GraphRepos, members: InMemoryCollectionMembers | None = None
) -> CountNodeTypes:
    guard = InMemoryAccessGuard()
    return CountNodeTypes(repos, guard, ListNodes(repos, guard, members))


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_returns_nothing_when_there_are_no_items() -> None:
    """Returns nothing when there are no items."""
    result = await _use_case(_repos()).handle(CountNodeTypesQuery(), ALICE)

    assert result == []


async def test_counts_each_type_for_the_actors_own_items_only() -> None:
    """Counts each type for the actors own items only."""
    repos = _repos()
    for owner, slug in (
        (ALICE.id, "film"),
        (ALICE.id, "film"),
        (ALICE.id, None),
        (BOB.id, "book"),
        (BOB.id, "film"),
    ):
        await repos.nodes.add(Node.create(owner_id=owner, name="n", type=slug))

    mine = await _use_case(repos).handle(CountNodeTypesQuery(), ALICE)
    theirs = await _use_case(repos).handle(CountNodeTypesQuery(), BOB)

    assert mine == [TypeCount(type="film", count=2), TypeCount(type=None, count=1)]
    assert theirs == [TypeCount(type="book", count=1), TypeCount(type="film", count=1)]


async def _shelf(repos: GraphRepos) -> list[Node]:
    nodes = [
        Node.create(owner_id=ALICE.id, name=name, type=slug)
        for name, slug in (("a", "film"), ("b", "film"), ("c", "book"), ("d", None))
    ]
    for node in nodes:
        await repos.nodes.add(node)
    return nodes


async def test_a_collection_counts_only_its_own_items() -> None:
    """A manual collection counts only the types of the items on it."""
    repos = _repos()
    members = InMemoryCollectionMembers()
    film, _, book, _ = await _shelf(repos)
    collection = uuid.uuid4()
    members.add_collection(collection, [film.id, book.id], owner_id=ALICE.id)

    result = await _use_case(repos, members).handle(
        CountNodeTypesQuery(collection=collection), ALICE
    )

    assert result == [TypeCount(type="book", count=1), TypeCount(type="film", count=1)]


async def test_an_empty_collection_counts_nothing() -> None:
    """A collection with no items has no types."""
    repos = _repos()
    members = InMemoryCollectionMembers()
    await _shelf(repos)
    collection = uuid.uuid4()
    members.add_collection(collection, [], owner_id=ALICE.id)

    result = await _use_case(repos, members).handle(
        CountNodeTypesQuery(collection=collection), ALICE
    )

    assert result == []


async def test_a_smart_collection_counts_the_items_matching_its_definition() -> None:
    """A smart collection counts the types of the items its query matches."""
    repos = _repos()
    members = InMemoryCollectionMembers()
    await _shelf(repos)
    collection = uuid.uuid4()
    films = {
        "v": 1,
        "where": {"op": "and", "children": [{"kind": "type", "in": ["film"]}]},
        "sort": [],
    }
    members.add_smart_collection(collection, films, owner_id=ALICE.id)

    result = await _use_case(repos, members).handle(
        CountNodeTypesQuery(collection=collection), ALICE
    )

    assert result == [TypeCount(type="film", count=2)]


async def test_a_smart_collection_that_no_longer_validates_counts_nothing() -> None:
    """A stale smart definition matches nothing, as it does in the list."""
    repos = _repos()
    members = InMemoryCollectionMembers()
    await _shelf(repos)
    collection = uuid.uuid4()
    members.add_smart_collection(
        collection, {"v": 99, "where": None, "sort": []}, owner_id=ALICE.id
    )

    result = await _use_case(repos, members).handle(
        CountNodeTypesQuery(collection=collection), ALICE
    )

    assert result == []


async def test_a_collection_that_is_not_the_actors_is_not_found() -> None:
    """Someone else's or a missing collection is not found."""
    repos = _repos()
    members = InMemoryCollectionMembers()
    theirs = uuid.uuid4()
    members.add_collection(theirs, [], owner_id=BOB.id)

    with pytest.raises(CollectionNotFoundError):
        await _use_case(repos, members).handle(
            CountNodeTypesQuery(collection=theirs), ALICE
        )
    with pytest.raises(CollectionNotFoundError):
        await _use_case(repos, members).handle(
            CountNodeTypesQuery(collection=uuid.uuid4()), ALICE
        )

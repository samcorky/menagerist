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
from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.domain.errors import CollectionNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_repos(nodes: InMemoryNodeRepository) -> GraphRepos:
    return GraphRepos(
        nodes=nodes,
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_list_nodes_filters_by_type() -> None:
    """ListNodes returns only nodes matching the requested type."""
    nodes = InMemoryNodeRepository()
    film = Node.create(name="Alien", type="film")
    person = Node.create(name="Ridley Scott", type="person")
    await nodes.add(film)
    await nodes.add(person)
    use_case = ListNodes(_make_repos(nodes))

    result = await use_case.handle(ListNodesQuery(type="film"), SYSTEM_ACTOR)

    assert result.items == [film]
    assert person not in result.items


async def test_list_nodes_filters_by_search_query() -> None:
    """ListNodes passes q to the repository and returns only matching nodes."""
    nodes = InMemoryNodeRepository()
    alien = Node.create(name="Alien", type="film")
    predator = Node.create(name="Predator", type="film")
    await nodes.add(alien)
    await nodes.add(predator)
    use_case = ListNodes(_make_repos(nodes))

    result = await use_case.handle(ListNodesQuery(q="alien"), SYSTEM_ACTOR)

    assert result.items == [alien]
    assert predator not in result.items


async def test_list_nodes_orders_by_id_and_paginates() -> None:
    """ListNodes returns node ordered by id, respecting after/limit."""
    nodes = InMemoryNodeRepository()
    node_list = [Node.create(name="Alien", type="film") for _ in range(3)]
    for node in node_list:
        await nodes.add(node)
    expected_order = sorted(node_list, key=lambda n: n.id)
    repos = _make_repos(nodes)
    use_case = ListNodes(repos)

    first_page = await use_case.handle(
        ListNodesQuery(after=None, limit=2), SYSTEM_ACTOR
    )

    assert first_page.items == expected_order[:2]

    second_page = await use_case.handle(
        ListNodesQuery(after=first_page.items[-1].id, limit=2), SYSTEM_ACTOR
    )

    assert second_page.items == expected_order[2:]


async def test_list_nodes_total_reflects_all_matching_nodes() -> None:
    """ListNodes.total counts all matches regardless of pagination limit."""
    nodes = InMemoryNodeRepository()
    for _ in range(5):
        await nodes.add(Node.create(name="Alien", type="film"))
    use_case = ListNodes(_make_repos(nodes))

    result = await use_case.handle(ListNodesQuery(limit=2), SYSTEM_ACTOR)

    assert len(result.items) == 2
    assert result.total == 5


async def _shelf_setup() -> tuple[
    InMemoryNodeRepository, InMemoryCollectionMembers, uuid.UUID, list[Node]
]:
    nodes = InMemoryNodeRepository()
    members = InMemoryCollectionMembers()
    on_shelf = [
        Node.create(name="Alien", type="film", favourite=True),
        Node.create(name="Aliens", type="film"),
        Node.create(name="Ridley Scott", type="person"),
    ]
    off_shelf = Node.create(name="Alien Nation", type="film", favourite=True)
    for node in [*on_shelf, off_shelf]:
        await nodes.add(node)
    collection_id = uuid.uuid4()
    members.add_collection(collection_id, [n.id for n in on_shelf])
    return nodes, members, collection_id, on_shelf


async def test_list_nodes_collection_restricts_to_members() -> None:
    """ListNodes with a collection returns only its items, and totals match."""
    nodes, members, collection_id, on_shelf = await _shelf_setup()
    use_case = ListNodes(_make_repos(nodes), members)

    result = await use_case.handle(
        ListNodesQuery(collection=collection_id), SYSTEM_ACTOR
    )

    assert result.items == sorted(on_shelf, key=lambda n: n.id)
    assert result.total == 3


async def test_list_nodes_collection_combines_with_other_filters() -> None:
    """The collection restriction combines with q, type and favourite."""
    nodes, members, collection_id, _ = await _shelf_setup()
    use_case = ListNodes(_make_repos(nodes), members)

    by_q = await use_case.handle(
        ListNodesQuery(collection=collection_id, q="alien"), SYSTEM_ACTOR
    )
    by_type = await use_case.handle(
        ListNodesQuery(collection=collection_id, type="person"), SYSTEM_ACTOR
    )
    by_fav = await use_case.handle(
        ListNodesQuery(collection=collection_id, favourite=True), SYSTEM_ACTOR
    )

    assert {n.name for n in by_q.items} == {"Alien", "Aliens"}
    assert by_q.total == 2
    assert [n.name for n in by_type.items] == ["Ridley Scott"]
    assert by_type.total == 1
    assert [n.name for n in by_fav.items] == ["Alien"]
    assert by_fav.total == 1


async def test_list_nodes_collection_paginates_with_restricted_total() -> None:
    """Paging walks the collection's items and total stays the restricted count."""
    nodes, members, collection_id, on_shelf = await _shelf_setup()
    use_case = ListNodes(_make_repos(nodes), members)
    ordered = sorted(on_shelf, key=lambda n: n.id)

    first = await use_case.handle(
        ListNodesQuery(collection=collection_id, limit=2), SYSTEM_ACTOR
    )
    second = await use_case.handle(
        ListNodesQuery(collection=collection_id, limit=2, after=first.items[-1].id),
        SYSTEM_ACTOR,
    )

    assert first.items == ordered[:2]
    assert second.items == ordered[2:]
    assert first.total == second.total == 3


async def test_list_nodes_unknown_collection_raises_not_found() -> None:
    """A collection the source does not know raises CollectionNotFoundError."""
    nodes, members, _, _ = await _shelf_setup()
    use_case = ListNodes(_make_repos(nodes), members)

    with pytest.raises(CollectionNotFoundError):
        await use_case.handle(ListNodesQuery(collection=uuid.uuid4()), SYSTEM_ACTOR)


async def test_list_nodes_empty_collection_returns_nothing() -> None:
    """A collection with no items yields an empty list and total 0."""
    nodes, members, _, _ = await _shelf_setup()
    empty_id = uuid.uuid4()
    members.add_collection(empty_id, [])
    use_case = ListNodes(_make_repos(nodes), members)

    result = await use_case.handle(ListNodesQuery(collection=empty_id), SYSTEM_ACTOR)

    assert result.items == []
    assert result.total == 0


async def test_list_nodes_collection_ignores_deleted_items() -> None:
    """A deleted item on the shelf is not listed or counted."""
    nodes, members, collection_id, on_shelf = await _shelf_setup()
    on_shelf[0].soft_delete()
    use_case = ListNodes(_make_repos(nodes), members)

    result = await use_case.handle(
        ListNodesQuery(collection=collection_id), SYSTEM_ACTOR
    )

    assert on_shelf[0] not in result.items
    assert result.total == 2


async def test_list_nodes_without_collection_is_unrestricted() -> None:
    """Without a collection the members source is not consulted."""
    nodes, members, _, _ = await _shelf_setup()
    use_case = ListNodes(_make_repos(nodes), members)

    result = await use_case.handle(ListNodesQuery(), SYSTEM_ACTOR)

    assert result.total == 4


async def test_list_nodes_collection_without_source_is_a_misconfiguration() -> None:
    """Filtering by collection without a members source fails loudly."""
    use_case = ListNodes(_make_repos(InMemoryNodeRepository()))

    with pytest.raises(RuntimeError, match="collection members"):
        await use_case.handle(ListNodesQuery(collection=uuid.uuid4()), SYSTEM_ACTOR)

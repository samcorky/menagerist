import uuid

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.domain.node import Node


async def test_add_and_get_round_trips() -> None:
    """A node added to the repository can be retrieved by id."""
    repository = InMemoryNodeRepository()
    node = Node.create(name="Alien", type="film")

    await repository.add(node)

    assert await repository.get(node.id) is node


async def test_get_returns_none_for_missing_node() -> None:
    """get() returns None for an id that was never added."""
    repository = InMemoryNodeRepository()

    assert await repository.get(uuid.uuid4()) is None


async def test_list_orders_by_id_ascending() -> None:
    """list() returns node ordered by id ascending, regardless of insert order."""
    repository = InMemoryNodeRepository()
    nodes = [Node.create(name="Alien", type="film") for _ in range(3)]
    for node in reversed(nodes):
        await repository.add(node)

    result = await repository.list(after=None, limit=10)

    assert result == sorted(nodes, key=lambda node: node.id)


async def test_list_respects_after_and_limit() -> None:
    """list() paginates using after/limit."""
    repository = InMemoryNodeRepository()
    nodes = sorted(
        (Node.create(name="Alien", type="film") for _ in range(4)), key=lambda n: n.id
    )
    for node in nodes:
        await repository.add(node)

    page = await repository.list(after=nodes[0].id, limit=2)

    assert page == nodes[1:3]


async def test_save_persists_changes_to_an_existing_node() -> None:
    """save() overwrites the stored node with the given instance."""
    repository = InMemoryNodeRepository()
    node = Node.create(name="Alien", type="film")
    await repository.add(node)

    node.name = "Alien (1979)"
    await repository.save(node)

    result = await repository.get(node.id)
    assert result is not None
    assert result.name == "Alien (1979)"


async def test_get_returns_none_for_a_soft_deleted_node() -> None:
    """get() treats a soft-deleted node as if it doesn't exist."""
    repository = InMemoryNodeRepository()
    node = Node.create(name="Alien", type="film")
    await repository.add(node)

    node.soft_delete()
    await repository.save(node)

    assert await repository.get(node.id) is None


async def test_list_excludes_soft_deleted_nodes() -> None:
    """list() omits soft-deleted node."""
    repository = InMemoryNodeRepository()
    kept = Node.create(name="Alien", type="film")
    deleted = Node.create(name="Predator", type="film")
    await repository.add(kept)
    await repository.add(deleted)

    deleted.soft_delete()
    await repository.save(deleted)

    result = await repository.list(after=None, limit=10)

    assert result == [kept]


async def test_list_filters_by_name_search() -> None:
    """list(q=...) returns nodes whose name contains the query (case-insensitive)."""
    repository = InMemoryNodeRepository()
    alien = Node.create(name="Alien", type="film")
    aliens = Node.create(name="Aliens", type="film")
    predator = Node.create(name="Predator", type="film")
    for node in (alien, aliens, predator):
        await repository.add(node)

    result = await repository.list(after=None, limit=10, q="alien")

    assert alien in result
    assert aliens in result
    assert predator not in result


async def test_list_filters_by_description_search() -> None:
    """list(q=...) matches against description as well as name."""
    repository = InMemoryNodeRepository()
    match = Node.create(name="Untitled", type="film", description="A Ridley Scott film")
    no_match = Node.create(
        name="Untitled 2", type="film", description="A James Cameron film"
    )
    for node in (match, no_match):
        await repository.add(node)

    result = await repository.list(after=None, limit=10, q="ridley")

    assert result == [match]


async def test_list_search_is_case_insensitive() -> None:
    """list(q=...) matches regardless of case in query or stored value."""
    repository = InMemoryNodeRepository()
    node = Node.create(name="ALIEN", type="film")
    await repository.add(node)

    result = await repository.list(after=None, limit=10, q="alien")

    assert result == [node]


async def test_list_search_combines_with_type_filter() -> None:
    """list(q=..., type=...) applies both filters independently."""
    repository = InMemoryNodeRepository()
    film = Node.create(name="Alien", type="film")
    person = Node.create(name="Alien character", type="person")
    for node in (film, person):
        await repository.add(node)

    result = await repository.list(after=None, limit=10, q="alien", type="film")

    assert result == [film]


async def test_count_returns_total_non_deleted() -> None:
    """count() returns the total number of non-deleted nodes."""
    repository = InMemoryNodeRepository()
    for _ in range(3):
        await repository.add(Node.create(name="Alien", type="film"))
    deleted = Node.create(name="Gone", type="film")
    await repository.add(deleted)
    deleted.soft_delete()
    await repository.save(deleted)

    assert await repository.count() == 3


async def test_count_filters_by_type() -> None:
    """count(type=...) returns only nodes of that type."""
    repository = InMemoryNodeRepository()
    await repository.add(Node.create(name="Alien", type="film"))
    await repository.add(Node.create(name="Aliens", type="film"))
    await repository.add(Node.create(name="Ridley Scott", type="person"))

    assert await repository.count(type="film") == 2
    assert await repository.count(type="person") == 1


async def test_count_filters_by_search_query() -> None:
    """count(q=...) counts only nodes matching the search."""
    repository = InMemoryNodeRepository()
    await repository.add(Node.create(name="Alien", type="film"))
    await repository.add(Node.create(name="Aliens", type="film"))
    await repository.add(Node.create(name="Predator", type="film"))

    assert await repository.count(q="alien") == 2


async def test_clear_type_nulls_out_matching_nodes() -> None:
    """clear_type() sets type to None for all nodes with the given slug."""
    repository = InMemoryNodeRepository()
    film1 = Node.create(name="Alien", type="film")
    film2 = Node.create(name="Aliens", type="film")
    person = Node.create(name="Ridley Scott", type="person")
    for node in (film1, film2, person):
        await repository.add(node)

    await repository.clear_type("film")

    assert film1.type is None
    assert film2.type is None
    assert person.type == "person"


async def test_clear_type_ignores_soft_deleted_nodes() -> None:
    """clear_type() does not touch soft-deleted nodes."""
    repository = InMemoryNodeRepository()
    deleted = Node.create(name="Gone", type="film")
    await repository.add(deleted)
    deleted.soft_delete()
    await repository.save(deleted)

    await repository.clear_type("film")

    assert deleted.type == "film"

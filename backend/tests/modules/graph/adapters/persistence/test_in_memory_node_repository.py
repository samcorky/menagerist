import uuid

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.domain.node import Node
from app.shared_kernel.access_scope import AccessScope


async def test_add_and_get_round_trips() -> None:
    """A node added to the repository can be retrieved by id."""
    repository = InMemoryNodeRepository()
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")

    await repository.add(node)

    assert await repository.get(node.id, scope=AccessScope.everyone()) is node


async def test_get_returns_none_for_missing_node() -> None:
    """get() returns None for an id that was never added."""
    repository = InMemoryNodeRepository()

    assert await repository.get(uuid.uuid4(), scope=AccessScope.everyone()) is None


async def test_list_orders_by_id_ascending() -> None:
    """list() returns node ordered by id ascending, regardless of insert order."""
    repository = InMemoryNodeRepository()
    nodes = [
        Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
        for _ in range(3)
    ]
    for node in reversed(nodes):
        await repository.add(node)

    result = await repository.list(scope=AccessScope.everyone(), after=None, limit=10)

    assert result == sorted(nodes, key=lambda node: node.id)


async def test_list_respects_after_and_limit() -> None:
    """list() paginates using after/limit."""
    repository = InMemoryNodeRepository()
    nodes = sorted(
        (
            Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
            for _ in range(4)
        ),
        key=lambda n: n.id,
    )
    for node in nodes:
        await repository.add(node)

    page = await repository.list(
        scope=AccessScope.everyone(), after=nodes[0].id, limit=2
    )

    assert page == nodes[1:3]


async def test_save_persists_changes_to_an_existing_node() -> None:
    """save() overwrites the stored node with the given instance."""
    repository = InMemoryNodeRepository()
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    await repository.add(node)

    node.name = "Alien (1979)"
    await repository.save(node)

    result = await repository.get(node.id, scope=AccessScope.everyone())
    assert result is not None
    assert result.name == "Alien (1979)"


async def test_get_returns_none_for_a_soft_deleted_node() -> None:
    """get() treats a soft-deleted node as if it doesn't exist."""
    repository = InMemoryNodeRepository()
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    await repository.add(node)

    node.soft_delete()
    await repository.save(node)

    assert await repository.get(node.id, scope=AccessScope.everyone()) is None


async def test_list_excludes_soft_deleted_nodes() -> None:
    """list() omits soft-deleted node."""
    repository = InMemoryNodeRepository()
    kept = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    deleted = Node.create(owner_id=uuid.UUID(int=1), name="Predator", type="film")
    await repository.add(kept)
    await repository.add(deleted)

    deleted.soft_delete()
    await repository.save(deleted)

    result = await repository.list(scope=AccessScope.everyone(), after=None, limit=10)

    assert result == [kept]


async def test_list_filters_by_name_search() -> None:
    """list(q=...) returns nodes whose name contains the query (case-insensitive)."""
    repository = InMemoryNodeRepository()
    alien = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    aliens = Node.create(owner_id=uuid.UUID(int=1), name="Aliens", type="film")
    predator = Node.create(owner_id=uuid.UUID(int=1), name="Predator", type="film")
    for node in (alien, aliens, predator):
        await repository.add(node)

    result = await repository.list(
        scope=AccessScope.everyone(), after=None, limit=10, q="alien"
    )

    assert alien in result
    assert aliens in result
    assert predator not in result


async def test_list_filters_by_description_search() -> None:
    """list(q=...) matches against description as well as name."""
    repository = InMemoryNodeRepository()
    match = Node.create(
        owner_id=uuid.UUID(int=1),
        name="Untitled",
        type="film",
        description="A Ridley Scott film",
    )
    no_match = Node.create(
        owner_id=uuid.UUID(int=1),
        name="Untitled 2",
        type="film",
        description="A James Cameron film",
    )
    for node in (match, no_match):
        await repository.add(node)

    result = await repository.list(
        scope=AccessScope.everyone(), after=None, limit=10, q="ridley"
    )

    assert result == [match]


async def test_list_search_is_case_insensitive() -> None:
    """list(q=...) matches regardless of case in query or stored value."""
    repository = InMemoryNodeRepository()
    node = Node.create(owner_id=uuid.UUID(int=1), name="ALIEN", type="film")
    await repository.add(node)

    result = await repository.list(
        scope=AccessScope.everyone(), after=None, limit=10, q="alien"
    )

    assert result == [node]


async def test_list_search_combines_with_type_filter() -> None:
    """list(q=..., type=...) applies both filters independently."""
    repository = InMemoryNodeRepository()
    film = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    person = Node.create(
        owner_id=uuid.UUID(int=1), name="Alien character", type="person"
    )
    for node in (film, person):
        await repository.add(node)

    result = await repository.list(
        scope=AccessScope.everyone(), after=None, limit=10, q="alien", type="film"
    )

    assert result == [film]


async def test_count_returns_total_non_deleted() -> None:
    """count() returns the total number of non-deleted nodes."""
    repository = InMemoryNodeRepository()
    for _ in range(3):
        await repository.add(
            Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
        )
    deleted = Node.create(owner_id=uuid.UUID(int=1), name="Gone", type="film")
    await repository.add(deleted)
    deleted.soft_delete()
    await repository.save(deleted)

    assert (
        await repository.count(
            scope=AccessScope.everyone(),
        )
        == 3
    )


async def test_count_filters_by_type() -> None:
    """count(type=...) returns only nodes of that type."""
    repository = InMemoryNodeRepository()
    await repository.add(
        Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    )
    await repository.add(
        Node.create(owner_id=uuid.UUID(int=1), name="Aliens", type="film")
    )
    await repository.add(
        Node.create(owner_id=uuid.UUID(int=1), name="Ridley Scott", type="person")
    )

    assert await repository.count(scope=AccessScope.everyone(), type="film") == 2
    assert await repository.count(scope=AccessScope.everyone(), type="person") == 1


async def test_count_filters_by_search_query() -> None:
    """count(q=...) counts only nodes matching the search."""
    repository = InMemoryNodeRepository()
    await repository.add(
        Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    )
    await repository.add(
        Node.create(owner_id=uuid.UUID(int=1), name="Aliens", type="film")
    )
    await repository.add(
        Node.create(owner_id=uuid.UUID(int=1), name="Predator", type="film")
    )

    assert await repository.count(scope=AccessScope.everyone(), q="alien") == 2


async def test_clear_type_nulls_out_matching_nodes() -> None:
    """clear_type() sets type to None for all nodes with the given slug."""
    repository = InMemoryNodeRepository()
    film1 = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    film2 = Node.create(owner_id=uuid.UUID(int=1), name="Aliens", type="film")
    person = Node.create(owner_id=uuid.UUID(int=1), name="Ridley Scott", type="person")
    for node in (film1, film2, person):
        await repository.add(node)

    await repository.clear_type("film", scope=AccessScope.everyone())

    assert film1.type is None
    assert film2.type is None
    assert person.type == "person"


async def test_clear_type_ignores_soft_deleted_nodes() -> None:
    """clear_type() does not touch soft-deleted nodes."""
    repository = InMemoryNodeRepository()
    deleted = Node.create(owner_id=uuid.UUID(int=1), name="Gone", type="film")
    await repository.add(deleted)
    deleted.soft_delete()
    await repository.save(deleted)

    await repository.clear_type("film", scope=AccessScope.everyone())

    assert deleted.type == "film"


async def test_count_and_list_with_attribute_filter_by_type_key_and_deletion() -> None:
    """Only live nodes of the type holding the key are counted and listed, by id."""
    repository = InMemoryNodeRepository()
    nodes = [
        Node.create(
            owner_id=uuid.UUID(int=1), name=f"n{i}", type="film", attributes={"k": i}
        )
        for i in range(3)
    ]
    other_type = Node.create(
        owner_id=uuid.UUID(int=1), name="o", type="book", attributes={"k": 1}
    )
    no_key = Node.create(
        owner_id=uuid.UUID(int=1), name="p", type="film", attributes={}
    )
    gone = Node.create(
        owner_id=uuid.UUID(int=1), name="q", type="film", attributes={"k": 9}
    )
    gone.soft_delete()
    for node in [*nodes, other_type, no_key, gone]:
        await repository.add(node)

    assert (
        await repository.count_with_attribute("film", "k", scope=AccessScope.everyone())
        == 3
    )
    page = await repository.list_with_attribute(
        "film", "k", after=None, limit=2, scope=AccessScope.everyone()
    )
    assert [n.id for n in page] == sorted(n.id for n in nodes)[:2]
    rest = await repository.list_with_attribute(
        "film", "k", after=page[-1].id, limit=10, scope=AccessScope.everyone()
    )
    assert [n.id for n in rest] == sorted(n.id for n in nodes)[2:]


async def test_count_with_attribute_can_match_a_value() -> None:
    """With `value`, only nodes whose attribute equals it are counted."""
    repository = InMemoryNodeRepository()
    for name, status in [("a", "Draft"), ("b", "Draft"), ("c", "Live")]:
        await repository.add(
            Node.create(
                owner_id=uuid.UUID(int=1),
                name=name,
                type="film",
                attributes={"s": status},
            )
        )

    assert (
        await repository.count_with_attribute(
            "film", "s", value="Draft", scope=AccessScope.everyone()
        )
        == 2
    )
    assert (
        await repository.count_with_attribute(
            "film", "s", value="Gone", scope=AccessScope.everyone()
        )
        == 0
    )
    assert (
        await repository.count_with_attribute("film", "s", scope=AccessScope.everyone())
        == 3
    )


async def test_count_with_attribute_value_matches_array_membership() -> None:
    """With `value`, an array holding it counts; a partial match does not."""
    repository = InMemoryNodeRepository()
    for name, held in [("a", ["CD", "Tape"]), ("b", ["Vinyl"]), ("c", "CD")]:
        await repository.add(
            Node.create(
                owner_id=uuid.UUID(int=1),
                name=name,
                type="film",
                attributes={"f": held},
            )
        )

    assert (
        await repository.count_with_attribute(
            "film", "f", value="CD", scope=AccessScope.everyone()
        )
        == 2
    )
    assert (
        await repository.count_with_attribute(
            "film", "f", value="C", scope=AccessScope.everyone()
        )
        == 0
    )


async def test_count_and_list_with_attribute_can_match_a_group_sub_key() -> None:
    """With `sub_key`, `key` names a group array and rows are matched instead."""
    repository = InMemoryNodeRepository()
    has_ingredient = Node.create(
        owner_id=uuid.UUID(int=1),
        name="a",
        type="recipe",
        attributes={"ingredients": [{"name": "Flour", "unit": "g"}]},
    )
    other_row_shape = Node.create(
        owner_id=uuid.UUID(int=1),
        name="b",
        type="recipe",
        attributes={"ingredients": [{"name": "Salt"}]},
    )
    empty_group = Node.create(
        owner_id=uuid.UUID(int=1),
        name="c",
        type="recipe",
        attributes={"ingredients": []},
    )
    not_a_list = Node.create(
        owner_id=uuid.UUID(int=1),
        name="d",
        type="recipe",
        attributes={"ingredients": "x"},
    )
    no_key = Node.create(
        owner_id=uuid.UUID(int=1), name="e", type="recipe", attributes={}
    )
    for node in [has_ingredient, other_row_shape, empty_group, not_a_list, no_key]:
        await repository.add(node)

    assert (
        await repository.count_with_attribute(
            "recipe", "ingredients", sub_key="unit", scope=AccessScope.everyone()
        )
        == 1
    )
    page = await repository.list_with_attribute(
        "recipe",
        "ingredients",
        sub_key="unit",
        after=None,
        limit=10,
        scope=AccessScope.everyone(),
    )
    assert [n.id for n in page] == [has_ingredient.id]

    assert (
        await repository.count_with_attribute(
            "recipe",
            "ingredients",
            sub_key="unit",
            value="g",
            scope=AccessScope.everyone(),
        )
        == 1
    )
    assert (
        await repository.count_with_attribute(
            "recipe",
            "ingredients",
            sub_key="unit",
            value="kg",
            scope=AccessScope.everyone(),
        )
        == 0
    )


async def test_list_attribute_values_counts_distinct_strings_most_used_first() -> None:
    """Only string values count; ordered by count desc then value asc."""
    repository = InMemoryNodeRepository()
    other_type = Node.create(
        owner_id=uuid.UUID(int=1), name="x", type="book", attributes={"status": "Draft"}
    )
    deleted = Node.create(
        owner_id=uuid.UUID(int=1), name="y", type="film", attributes={"status": "Draft"}
    )
    deleted.soft_delete()
    for node in [
        Node.create(
            owner_id=uuid.UUID(int=1),
            name="a",
            type="film",
            attributes={"status": "Draft"},
        ),
        Node.create(
            owner_id=uuid.UUID(int=1),
            name="b",
            type="film",
            attributes={"status": "Draft"},
        ),
        Node.create(
            owner_id=uuid.UUID(int=1),
            name="c",
            type="film",
            attributes={"status": "Live"},
        ),
        Node.create(
            owner_id=uuid.UUID(int=1), name="d", type="film", attributes={"status": 1}
        ),
        Node.create(owner_id=uuid.UUID(int=1), name="e", type="film", attributes={}),
        other_type,
        deleted,
    ]:
        await repository.add(node)

    values = await repository.list_attribute_values(
        "film", "status", scope=AccessScope.everyone()
    )

    assert values == [("Draft", 2), ("Live", 1)]


async def test_list_attribute_values_filters_by_q_and_limit() -> None:
    """`q` filters case-insensitively by substring; `limit` caps the results."""
    repository = InMemoryNodeRepository()
    for name, status in [("a", "Draft"), ("b", "Draft"), ("c", "Live")]:
        await repository.add(
            Node.create(
                owner_id=uuid.UUID(int=1),
                name=name,
                type="film",
                attributes={"status": status},
            )
        )

    assert await repository.list_attribute_values(
        "film", "status", q="live", scope=AccessScope.everyone()
    ) == [("Live", 1)]
    assert await repository.list_attribute_values(
        "film", "status", limit=1, scope=AccessScope.everyone()
    ) == [("Draft", 2)]


async def _seed_for_ids() -> tuple[InMemoryNodeRepository, list[Node]]:
    """Add four nodes (film, film, film favourite, book) and return them by id order."""
    repository = InMemoryNodeRepository()
    nodes = [
        Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film"),
        Node.create(owner_id=uuid.UUID(int=1), name="Aliens", type="film"),
        Node.create(
            owner_id=uuid.UUID(int=1), name="Blade Runner", type="film", favourite=True
        ),
        Node.create(owner_id=uuid.UUID(int=1), name="Dune", type="book"),
    ]
    for node in nodes:
        await repository.add(node)
    return repository, nodes


async def test_ids_restricts_list_and_count() -> None:
    """`ids` limits list() and count() to those nodes, in id order."""
    repository, nodes = await _seed_for_ids()
    wanted = {nodes[3].id, nodes[1].id}

    result = await repository.list(
        scope=AccessScope.everyone(), after=None, limit=10, ids=wanted
    )

    assert [n.id for n in result] == [nodes[1].id, nodes[3].id]
    assert await repository.count(scope=AccessScope.everyone(), ids=wanted) == 2


async def test_ids_none_means_no_restriction() -> None:
    """`ids=None` applies no id restriction."""
    repository, nodes = await _seed_for_ids()

    assert len(
        await repository.list(
            scope=AccessScope.everyone(), after=None, limit=10, ids=None
        )
    ) == len(nodes)
    assert await repository.count(scope=AccessScope.everyone(), ids=None) == len(nodes)


async def test_empty_ids_returns_nothing() -> None:
    """An empty `ids` collection yields no results and a zero count."""
    repository, _ = await _seed_for_ids()

    assert (
        await repository.list(
            scope=AccessScope.everyone(), after=None, limit=10, ids=set()
        )
        == []
    )
    assert await repository.count(scope=AccessScope.everyone(), ids=set()) == 0


async def test_ids_ignores_unknown_and_deleted_nodes() -> None:
    """Ids of missing or soft-deleted nodes never appear."""
    repository, nodes = await _seed_for_ids()
    nodes[0].soft_delete()
    await repository.save(nodes[0])
    wanted = [nodes[0].id, nodes[1].id, uuid.uuid4()]

    result = await repository.list(
        scope=AccessScope.everyone(), after=None, limit=10, ids=wanted
    )

    assert [n.id for n in result] == [nodes[1].id]
    assert await repository.count(scope=AccessScope.everyone(), ids=wanted) == 1


async def test_ids_combines_with_other_filters() -> None:
    """`ids` is ANDed with type, q, favourite, after and limit."""
    repository, nodes = await _seed_for_ids()
    everything = {n.id for n in nodes}
    films = {nodes[0].id, nodes[1].id, nodes[3].id}

    by_type = await repository.list(
        scope=AccessScope.everyone(), after=None, limit=10, ids=films, type="film"
    )
    assert [n.id for n in by_type] == [nodes[0].id, nodes[1].id]
    assert (
        await repository.count(scope=AccessScope.everyone(), ids=films, type="film")
        == 2
    )

    by_q = await repository.list(
        scope=AccessScope.everyone(), after=None, limit=10, ids=films, q="alien"
    )
    assert [n.id for n in by_q] == [nodes[0].id, nodes[1].id]
    assert (
        await repository.count(scope=AccessScope.everyone(), ids=films, q="alien") == 2
    )

    by_fav = await repository.list(
        scope=AccessScope.everyone(), after=None, limit=10, ids=films, favourite=True
    )
    assert by_fav == []
    assert (
        await repository.count(
            scope=AccessScope.everyone(), ids=everything, favourite=True
        )
        == 1
    )

    paged = await repository.list(
        scope=AccessScope.everyone(), after=nodes[0].id, limit=1, ids=films
    )
    assert [n.id for n in paged] == [nodes[1].id]
    nxt = await repository.list(
        scope=AccessScope.everyone(), after=nodes[1].id, limit=5, ids=films
    )
    assert [n.id for n in nxt] == [nodes[3].id]


async def test_search_ignores_accents_both_ways() -> None:
    """Accented text matches plain `q` and vice versa, in name, description, values."""
    repository = InMemoryNodeRepository()
    by_name = Node.create(owner_id=uuid.UUID(int=1), name="Café", type="film")
    by_description = Node.create(
        owner_id=uuid.UUID(int=1), name="X", description="Crème brûlée"
    )
    by_value = Node.create(
        owner_id=uuid.UUID(int=1), name="Y", type="film", attributes={"director": "Zoë"}
    )
    plain = Node.create(owner_id=uuid.UUID(int=1), name="Cafe plain")
    percent = Node.create(owner_id=uuid.UUID(int=1), name="50% café")
    for node in (by_name, by_description, by_value, plain, percent):
        await repository.add(node)

    async def ids(q: str) -> set[object]:
        found = await repository.list(
            scope=AccessScope.everyone(), after=None, limit=10, q=q
        )
        return {n.id for n in found}

    assert await ids("cafe") == {by_name.id, plain.id, percent.id}
    assert await ids("CAFÉ") == {by_name.id, plain.id, percent.id}
    assert await ids("creme brulee") == {by_description.id}
    assert await ids("zoe") == {by_value.id}
    assert await ids("zoë") == {by_value.id}
    assert await ids("50% cafe") == {percent.id}
    assert await repository.count(scope=AccessScope.everyone(), q="cafe") == 3


async def test_list_attribute_values_q_ignores_accents() -> None:
    """Attribute value suggestions fold accents in both directions."""
    repository = InMemoryNodeRepository()
    await repository.add(
        Node.create(
            owner_id=uuid.UUID(int=1), name="a", type="film", attributes={"s": "Zoë"}
        )
    )
    await repository.add(
        Node.create(
            owner_id=uuid.UUID(int=1), name="b", type="film", attributes={"s": "Zoe"}
        )
    )

    assert await repository.list_attribute_values(
        "film", "s", q="zoe", scope=AccessScope.everyone()
    ) == [
        ("Zoe", 1),
        ("Zoë", 1),
    ]
    assert await repository.list_attribute_values(
        "film", "s", q="ZOË", scope=AccessScope.everyone()
    ) == [
        ("Zoe", 1),
        ("Zoë", 1),
    ]

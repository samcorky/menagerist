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
        node.extra_schema,
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


async def test_add_and_get_round_trips_a_null_extra_schema(
    db_session: AsyncSession,
) -> None:
    """A node with no overlay stores and returns `extra_schema` as None."""
    repository = SqlAlchemyNodeRepository(db_session)
    node = Node.create(name="Alien", type="film")

    await repository.add(node)
    result = await repository.get(node.id)

    assert result is not None
    assert result.extra_schema is None


async def test_add_and_get_round_trips_an_extra_schema(
    db_session: AsyncSession,
) -> None:
    """A node's per-item overlay schema survives a round trip through JSONB."""
    repository = SqlAlchemyNodeRepository(db_session)
    schema = {
        "type": "object",
        "properties": {"signed": {"type": "boolean", "x-menagerist": {}}},
    }
    node = Node.create(name="Alien", type="film", extra_schema=schema)

    await repository.add(node)
    result = await repository.get(node.id)

    assert result is not None
    assert result.extra_schema == schema


async def test_save_persists_a_changed_extra_schema(db_session: AsyncSession) -> None:
    """Updating extra_schema on an existing node and saving it persists the change."""
    repository = SqlAlchemyNodeRepository(db_session)
    node = Node.create(name="Alien", type="film")
    await repository.add(node)

    node.update(extra_schema={"type": "object", "properties": {}})
    await repository.save(node)
    result = await repository.get(node.id)

    assert result is not None
    assert result.extra_schema == {"type": "object", "properties": {}}


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


async def test_count_and_list_with_attribute_can_match_a_group_sub_key(
    db_session: AsyncSession,
) -> None:
    """With `sub_key`, `key` names a group array and its rows are matched instead."""
    repository = SqlAlchemyNodeRepository(db_session)
    has_ingredient = Node.create(
        name="a",
        type="recipe",
        attributes={"ingredients": [{"name": "Flour", "unit": "g"}]},
    )
    other_row_shape = Node.create(
        name="b", type="recipe", attributes={"ingredients": [{"name": "Salt"}]}
    )
    for node in [
        has_ingredient,
        other_row_shape,
        Node.create(name="c", type="recipe", attributes={"ingredients": []}),
        Node.create(name="d", type="recipe", attributes={}),
    ]:
        await repository.add(node)

    assert (
        await repository.count_with_attribute("recipe", "ingredients", sub_key="unit")
        == 1
    )
    page = await repository.list_with_attribute(
        "recipe", "ingredients", sub_key="unit", after=None, limit=10
    )
    assert [n.id for n in page] == [has_ingredient.id]
    assert (
        await repository.count_with_attribute(
            "recipe", "ingredients", sub_key="unit", value="g"
        )
        == 1
    )
    assert (
        await repository.count_with_attribute(
            "recipe", "ingredients", sub_key="unit", value="kg"
        )
        == 0
    )


_BACKSLASH = chr(92)
_EXCLUSIONS = {"film": ["old_note", "internal", "stars"]}


async def _search_ids(
    repository: SqlAlchemyNodeRepository,
    q: str,
    exclusions: dict[str, list[str]] | None = None,
) -> list[uuid.UUID]:
    listed = await repository.list(
        after=None, limit=50, q=q, attribute_search_exclusions=exclusions
    )
    counted = await repository.count(q=q, attribute_search_exclusions=exclusions)
    assert counted == len(listed), q
    return [node.id for node in listed]


async def test_search_matches_attribute_values_but_not_keys(
    db_session: AsyncSession,
) -> None:
    """Strings, numbers and group cells match; key names, booleans and nulls do not."""
    repository = SqlAlchemyNodeRepository(db_session)
    film = Node.create(
        name="Alien",
        type="film",
        attributes={
            "director": "Ridley Scott",
            "year": 1979,
            "seen": True,
            "nothing": None,
            "cast": [{"name": "Sigourney Weaver", "role": "Ripley"}],
        },
    )
    await repository.add(film)

    for q in ("scott", "1979", "ripley", "WEAVER"):
        assert await _search_ids(repository, q) == [film.id], q
    for q in ("director", "true", "seen", "nothing", "role", "null"):
        assert await _search_ids(repository, q) == [], q


async def test_search_exclusions_apply_only_to_their_type(
    db_session: AsyncSession,
) -> None:
    """Excluded keys are skipped for that type; the same key elsewhere still matches."""
    repository = SqlAlchemyNodeRepository(db_session)
    film = Node.create(
        name="Alien",
        type="film",
        attributes={"old_note": "gooey", "internal": "secret", "stars": 5},
    )
    person = Node.create(name="Ripley", type="person", attributes={"old_note": "gooey"})
    untyped = Node.create(name="Loose", attributes={"internal": "secret"})
    for node in (film, person, untyped):
        await repository.add(node)

    assert await _search_ids(repository, "gooey", _EXCLUSIONS) == [person.id]
    assert await _search_ids(repository, "secret", _EXCLUSIONS) == [untyped.id]
    assert await _search_ids(repository, "5", _EXCLUSIONS) == []
    assert sorted(await _search_ids(repository, "gooey")) == sorted(
        [film.id, person.id]
    )


async def test_search_still_matches_name_and_description(
    db_session: AsyncSession,
) -> None:
    """A type with exclusions can still be found by name and description."""
    repository = SqlAlchemyNodeRepository(db_session)
    film = Node.create(name="Alien", type="film", description="a xenomorph")
    await repository.add(film)

    assert await _search_ids(repository, "alien", _EXCLUSIONS) == [film.id]
    assert await _search_ids(repository, "xeno", _EXCLUSIONS) == [film.id]


async def test_search_treats_like_wildcards_and_backslash_literally(
    db_session: AsyncSession,
) -> None:
    """`%`, `_` and the escape character in the query match only themselves."""
    repository = SqlAlchemyNodeRepository(db_session)
    pct = Node.create(name="100% sure")
    under = Node.create(name="a_b")
    slash = Node.create(name="x", attributes={"path": "c:" + _BACKSLASH + "temp"})
    plain = Node.create(name="Plain")
    for node in (pct, under, slash, plain):
        await repository.add(node)

    assert await _search_ids(repository, "%") == [pct.id]
    assert await _search_ids(repository, "_") == [under.id]
    assert await _search_ids(repository, _BACKSLASH) == [slash.id]
    assert await _search_ids(repository, _BACKSLASH + "temp") == [slash.id]


async def test_search_ignores_deleted_nodes(db_session: AsyncSession) -> None:
    """Soft-deleted nodes never match."""
    repository = SqlAlchemyNodeRepository(db_session)
    node = Node.create(name="Gone", attributes={"note": "findme"})
    node.deleted_at = node.created_at
    await repository.add(node)

    assert await _search_ids(repository, "findme") == []

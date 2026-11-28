import uuid
from datetime import date
from typing import Any

import pytest

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
from app.modules.graph.application.aggregate_nodes import (
    AggregateNodes,
    AggregateNodesQuery,
)
from app.modules.graph.domain.aggregate import CurrencyValue, MeasureValue
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.domain.query import InvalidQueryError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

ALICE = Actor(id=uuid.UUID(int=11), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=12), roles=frozenset({"member"}))

_MONEY = {
    "type": "object",
    "x-menagerist": {"kind": "money", "origin": {"preset": "p1"}},
}
FILM: dict[str, Any] = {
    "type": "object",
    "properties": {
        "price": _MONEY,
        "rating": {"type": "number", "x-menagerist": {"kind": "rating"}},
        "seen": {"type": "string", "format": "date"},
        "format": {"type": "string", "enum": ["dvd", "bluray"]},
        "owned": {"type": "boolean"},
        "old": {"type": "number", "x-menagerist": {"archived": True}},
    },
}
BOOK: dict[str, Any] = {"type": "object", "properties": {"cost": _MONEY}}
EVERYTHING: dict[str, Any] = {"v": 1}
FILMS: dict[str, Any] = {
    "v": 1,
    "where": {"op": "and", "children": [{"kind": "type", "in": ["film"]}]},
}


def _gbp(value: float) -> dict[str, Any]:
    return {"value": value, "currency": "GBP"}


async def _world() -> AggregateNodes:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    for slug, schema, parent in (
        ("film", FILM, None),
        ("book", BOOK, None),
        ("documentary", None, "film"),
    ):
        await repos.node_types.add(
            NodeType.create(
                owner_id=ALICE.id,
                slug=slug,
                label=slug.title(),
                attributes_schema=schema,
                parent=parent,
            )
        )
    items: list[tuple[str, str, dict[str, Any]]] = [
        ("A", "film", {"price": _gbp(10), "rating": 4, "seen": "2020-01-05"}),
        ("B", "film", {"price": _gbp(20.5), "rating": 2, "owned": True}),
        ("C", "film", {"price": {"value": 5, "currency": "USD"}, "seen": "2019-12-31"}),
        ("D", "book", {"cost": _gbp(7)}),
        ("E", "film", {}),
        ("F", "documentary", {"price": _gbp(1.25), "rating": 4}),
    ]
    for name, type_slug, attributes in items:
        await repos.nodes.add(
            Node.create(
                owner_id=ALICE.id, name=name, type=type_slug, attributes=attributes
            )
        )
    await repos.nodes.add(
        Node.create(
            owner_id=BOB.id, name="theirs", type="film", attributes={"price": _gbp(999)}
        )
    )
    return AggregateNodes(
        repos, InMemoryAccessGuard(), today=lambda: date(2026, 11, 28)
    )


async def _one(
    measure: dict[str, Any],
    query: dict[str, Any] = EVERYTHING,
    actor: Actor = ALICE,
) -> MeasureValue:
    use_case = await _world()
    result = await use_case.handle(
        AggregateNodesQuery(query=query, measures=[measure]), actor
    )
    return result.values[0]


def _money(*pairs: tuple[str, float]) -> MeasureValue:
    return MeasureValue(
        currencies=tuple(CurrencyValue(currency=c, value=v) for c, v in pairs)
    )


async def test_counts_the_items_the_query_matches() -> None:
    """A count with no field counts items, and the result says how many matched."""
    use_case = await _world()

    result = await use_case.handle(
        AggregateNodesQuery(query=FILMS, measures=[{"fn": "count"}]), ALICE
    )

    # The documentary is a film, so a type condition on film matches it too.
    assert result.items == 5
    assert result.values == [MeasureValue(value=5)]


async def test_totals_money_one_currency_at_a_time() -> None:
    """Amounts are never converted, so each currency has its own total."""
    value = await _one({"fn": "sum", "type": "film", "key": "price"})

    # The documentary is a subtype, so its price counts; Bob's does not.
    assert value == _money(("GBP", 31.75), ("USD", 5))


async def test_a_saved_field_totals_across_types_and_keys() -> None:
    """Every type field copied from the saved field is read, whatever its key."""
    value = await _one({"fn": "sum", "origin": "p1"})

    assert value == _money(("GBP", 38.75), ("USD", 5))


async def test_the_query_narrows_what_is_totalled() -> None:
    """Only the items the query matches are read."""
    value = await _one({"fn": "sum", "type": "film", "key": "price"}, FILMS)

    assert value == _money(("GBP", 31.75), ("USD", 5))
    books = {
        "v": 1,
        "where": {"op": "and", "children": [{"kind": "type", "in": ["book"]}]},
    }
    assert await _one({"fn": "sum", "type": "film", "key": "price"}, books) == _money()


async def test_averages_only_the_items_that_have_a_value() -> None:
    """Items with no rating are not counted as zero."""
    value = await _one({"fn": "avg", "type": "film", "key": "rating"})

    assert value == MeasureValue(value=3.333333)


@pytest.mark.parametrize(
    ("measure", "expected"),
    [
        ({"fn": "min", "type": "film", "key": "rating"}, 2),
        ({"fn": "max", "type": "film", "key": "rating"}, 4),
        ({"fn": "sum", "type": "film", "key": "rating"}, 10),
        ({"fn": "count", "type": "film", "key": "rating"}, 3),
        ({"fn": "distinct", "type": "film", "key": "rating"}, 2),
        ({"fn": "min", "type": "film", "key": "seen"}, "2019-12-31"),
        ({"fn": "max", "type": "film", "key": "seen"}, "2020-01-05"),
        ({"fn": "count", "type": "film", "key": "owned"}, 1),
        ({"fn": "distinct", "type": "film", "key": "seen"}, 2),
    ],
)
async def test_reads_each_kind_of_field(
    measure: dict[str, Any], expected: float | str
) -> None:
    """Numbers, dates and yes/no values each answer the functions that fit them."""
    value = await _one(measure)

    assert value.value == expected


async def test_money_has_its_own_minimum_and_count_of_amounts() -> None:
    """Min and max are per currency; a count is of the items that have a price."""
    use_case = await _world()

    result = await use_case.handle(
        AggregateNodesQuery(
            measures=[
                {"fn": "min", "type": "film", "key": "price"},
                {"fn": "max", "type": "film", "key": "price"},
                {"fn": "count", "type": "film", "key": "price"},
            ]
        ),
        ALICE,
    )

    assert result.values == [
        _money(("GBP", 1.25), ("USD", 5)),
        _money(("GBP", 20.5), ("USD", 5)),
        MeasureValue(value=4),
    ]


async def test_no_value_to_read_gives_none_not_zero() -> None:
    """An average of nothing is no number; a count of nothing is 0."""
    nothing = {
        "v": 1,
        "where": {"op": "and", "children": [{"kind": "type", "in": ["book"]}]},
    }

    average = await _one({"fn": "avg", "type": "film", "key": "rating"}, nothing)
    count = await _one({"fn": "count", "type": "film", "key": "rating"}, nothing)

    assert average == MeasureValue(value=None)
    assert count == MeasureValue(value=0)


async def test_aggregates_only_the_actors_own_items_and_types() -> None:
    """Bob's items are his alone, and Alice's item types are not his to read."""
    use_case = await _world()

    result = await use_case.handle(
        AggregateNodesQuery(
            measures=[{"fn": "count"}, {"fn": "sum", "type": "film", "key": "price"}]
        ),
        BOB,
    )

    assert result.items == 1
    assert result.values == [MeasureValue(value=1), MeasureValue()]
    assert [w.path for w in result.warnings] == ["measures[1]"]


async def test_a_field_that_is_gone_is_a_warning_with_no_value() -> None:
    """An archived or missing field matches nothing, as in a search."""
    use_case = await _world()

    result = await use_case.handle(
        AggregateNodesQuery(
            measures=[
                {"fn": "sum", "type": "film", "key": "old"},
                {"fn": "sum", "type": "film", "key": "price"},
                {"fn": "sum", "origin": "nope"},
            ]
        ),
        ALICE,
    )

    assert result.values[0] == MeasureValue()
    assert result.values[2] == MeasureValue()
    assert [w.path for w in result.warnings] == ["measures[0]", "measures[2]"]


@pytest.mark.parametrize(
    ("measure", "path", "message"),
    [
        ({"fn": "sum", "type": "film", "key": "seen"}, "measures[0]", "cannot read"),
        ({"fn": "sum", "type": "film", "key": "format"}, "measures[0]", "cannot read"),
        ({"fn": "avg", "type": "film", "key": "owned"}, "measures[0]", "cannot read"),
        ({"fn": "sum"}, "measures[0]", "needs a field"),
        ({"fn": "median", "key": "x", "type": "film"}, "measures[0]", "`fn` is one of"),
        ({"fn": "sum", "type": "film"}, "measures[0]", "needs both"),
        ({"fn": "sum", "origin": "p1", "key": "x"}, "measures[0]", "not both"),
        ({"fn": "sum", "type": "film", "key": ""}, "measures[0]", "non-empty"),
        (
            {"fn": "sum", "type": "film", "key": "price", "x": 1},
            "measures[0]",
            "Unknown",
        ),
    ],
)
async def test_refuses_a_measure_that_does_not_fit(
    measure: dict[str, Any], path: str, message: str
) -> None:
    """A malformed measure, or a function the field's kind cannot answer, is a 400."""
    use_case = await _world()

    with pytest.raises(InvalidQueryError, match=message) as raised:
        await use_case.handle(AggregateNodesQuery(measures=[measure]), ALICE)

    assert raised.value.path == path


@pytest.mark.parametrize("measures", [[], [{"fn": "count"}] * 11, ["sum"]])
async def test_refuses_no_measures_too_many_or_a_non_object(
    measures: list[object],
) -> None:
    """One to ten measures, each an object."""
    use_case = await _world()

    with pytest.raises(InvalidQueryError):
        await use_case.handle(AggregateNodesQuery(measures=measures), ALICE)


async def test_refuses_a_saved_field_of_mixed_kinds() -> None:
    """One answer cannot be both a total and a text count, so the kinds must agree."""
    use_case = await _world()
    use_case._repos.node_types  # noqa: B018 - the world holds its repos
    repos = use_case._repos
    await repos.node_types.add(
        NodeType.create(
            owner_id=ALICE.id,
            slug="game",
            label="Game",
            attributes_schema={
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "x-menagerist": {"origin": {"preset": "p1"}},
                    }
                },
            },
        )
    )

    with pytest.raises(InvalidQueryError, match="different kinds"):
        await use_case.handle(
            AggregateNodesQuery(measures=[{"fn": "count", "origin": "p1"}]), ALICE
        )


async def test_a_bad_query_is_refused_like_a_search_refuses_it() -> None:
    """The query goes through the search parser."""
    use_case = await _world()

    with pytest.raises(InvalidQueryError):
        await use_case.handle(
            AggregateNodesQuery(query={"v": 9}, measures=[{"fn": "count"}]), ALICE
        )

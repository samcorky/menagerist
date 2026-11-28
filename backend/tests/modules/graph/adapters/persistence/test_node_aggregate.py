"""Aggregate measures give the same answers in memory and in Postgres.

The in-memory evaluator is the reference. The data includes values of the wrong
shape (text where a number goes, an amount with no currency), which both leave out.
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any, cast

import pytest

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.aggregate import (
    AggregateFn,
    CurrencyValue,
    Measure,
    MeasureSource,
    MeasureValue,
    ResolvedMeasure,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import Query, ResolvedQuery
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=701)
BOB = uuid.UUID(int=702)


def _gbp(value: object) -> dict[str, Any]:
    return {"value": value, "currency": "GBP"}


# (type, attributes); the types stand in for what a measure's sources name.
_DATA: list[tuple[str, dict[str, Any]]] = [
    ("film", {"price": _gbp(10), "rating": 4, "seen": "2020-01-05", "owned": True}),
    ("film", {"price": _gbp(20.5), "rating": 2, "seen": "2019-12-31", "owned": False}),
    ("film", {"price": {"value": 5, "currency": "USD"}, "rating": 4}),
    ("film", {"price": _gbp(0.1), "format": "dvd"}),
    ("film", {"price": _gbp(0.2), "format": "Dvd"}),
    ("film", {"price": {"value": 9}, "rating": "abc", "seen": 1999, "owned": "yes"}),
    ("film", {"price": _gbp("12"), "rating": True}),
    ("film", {}),
    ("subfilm", {"price": _gbp(1.25), "rating": 3}),
    ("book", {"cost": _gbp(7), "rating": 100}),
]


def _measure(
    fn: str,
    kind: str | None,
    *sources: tuple[tuple[str, ...], str],
) -> ResolvedMeasure:
    named = Measure(
        fn=cast("AggregateFn", fn), type="film", key=sources[0][1] if sources else None
    )
    return ResolvedMeasure(
        measure=named,
        kind=kind,
        sources=tuple(MeasureSource(types=t, key=k) for t, k in sources),
    )


FILMS = ("film", "subfilm")
CASES: list[tuple[str, ResolvedMeasure, MeasureValue]] = [
    ("count items", _measure("count", None), MeasureValue(value=10)),
    (
        "sum money per currency",
        _measure("sum", "money", (FILMS, "price")),
        MeasureValue(
            currencies=(
                CurrencyValue(currency="GBP", value=32.05),
                CurrencyValue(currency="USD", value=5),
            )
        ),
    ),
    (
        "money across keys and types",
        _measure("sum", "money", (FILMS, "price"), (("book",), "cost")),
        MeasureValue(
            currencies=(
                CurrencyValue(currency="GBP", value=39.05),
                CurrencyValue(currency="USD", value=5),
            )
        ),
    ),
    (
        "avg money",
        _measure("avg", "money", (FILMS, "price")),
        MeasureValue(
            currencies=(
                CurrencyValue(currency="GBP", value=6.41),
                CurrencyValue(currency="USD", value=5),
            )
        ),
    ),
    (
        "min money",
        _measure("min", "money", (FILMS, "price")),
        MeasureValue(
            currencies=(
                CurrencyValue(currency="GBP", value=0.1),
                CurrencyValue(currency="USD", value=5),
            )
        ),
    ),
    (
        "max money",
        _measure("max", "money", (FILMS, "price")),
        MeasureValue(
            currencies=(
                CurrencyValue(currency="GBP", value=20.5),
                CurrencyValue(currency="USD", value=5),
            )
        ),
    ),
    (
        "count money",
        _measure("count", "money", (FILMS, "price")),
        MeasureValue(value=6),
    ),
    (
        "decimal sums do not drift",
        _measure("sum", "money", (("film",), "price")),
        MeasureValue(
            currencies=(
                CurrencyValue(currency="GBP", value=30.8),
                CurrencyValue(currency="USD", value=5),
            )
        ),
    ),
    (
        "sum rating",
        _measure("sum", "rating", (FILMS, "rating")),
        MeasureValue(value=13),
    ),
    (
        "avg rating",
        _measure("avg", "rating", (FILMS, "rating")),
        MeasureValue(value=3.25),
    ),
    ("min rating", _measure("min", "rating", (FILMS, "rating")), MeasureValue(value=2)),
    ("max rating", _measure("max", "rating", (FILMS, "rating")), MeasureValue(value=4)),
    (
        "count rating",
        _measure("count", "rating", (FILMS, "rating")),
        MeasureValue(value=4),
    ),
    (
        "distinct rating",
        _measure("distinct", "rating", (FILMS, "rating")),
        MeasureValue(value=3),
    ),
    (
        "min date",
        _measure("min", "date", (FILMS, "seen")),
        MeasureValue(value="2019-12-31"),
    ),
    (
        "max date",
        _measure("max", "date", (FILMS, "seen")),
        MeasureValue(value="2020-01-05"),
    ),
    (
        "distinct text is case sensitive",
        _measure("distinct", "choice", (FILMS, "format")),
        MeasureValue(value=2),
    ),
    (
        "count yes/no",
        _measure("count", "boolean", (FILMS, "owned")),
        MeasureValue(value=2),
    ),
    (
        "distinct yes/no",
        _measure("distinct", "boolean", (FILMS, "owned")),
        MeasureValue(value=2),
    ),
    (
        "a sum of nothing is none",
        _measure("sum", "rating", (("book",), "missing")),
        MeasureValue(value=None),
    ),
    (
        "an average of nothing is none",
        _measure("avg", "rating", (("book",), "missing")),
        MeasureValue(value=None),
    ),
    (
        "a count of nothing is 0",
        _measure("count", "rating", (("book",), "missing")),
        MeasureValue(value=0),
    ),
    (
        "money of nothing has no currencies",
        _measure("sum", "money", (("book",), "missing")),
        MeasureValue(),
    ),
]


def _resolved() -> ResolvedQuery:
    return ResolvedQuery(
        query=Query(where=None),
        field_kinds={},
        search_exclusions={},
        today=date(2026, 11, 28),
        stale=frozenset(),
    )


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repository(request: pytest.FixtureRequest) -> NodeRepository:
    """The same scenarios run against both adapters (empty until `_seed`)."""
    if request.param == "in_memory":
        return InMemoryNodeRepository()
    return SqlAlchemyNodeRepository(request.getfixturevalue("db_session"))


async def _seed(repo: NodeRepository) -> NodeRepository:
    for n, (type_slug, attributes) in enumerate(_DATA):
        await repo.add(
            Node.create(
                owner_id=ALICE, name=f"Item {n}", type=type_slug, attributes=attributes
            )
        )
    await repo.add(
        Node.create(
            owner_id=BOB, name="Theirs", type="film", attributes={"price": _gbp(999)}
        )
    )
    return repo


@pytest.mark.parametrize(
    ("measure", "expected"), [c[1:] for c in CASES], ids=[c[0] for c in CASES]
)
async def test_measure(
    repository: NodeRepository, measure: ResolvedMeasure, expected: MeasureValue
) -> None:
    """Each measure gives the same answer in both adapters, Bob's items left out."""
    await _seed(repository)

    answers = await repository.aggregate(
        scope=ContentFilter.of(ALICE), resolved=_resolved(), measures=[measure]
    )

    assert answers == [expected]


async def test_several_measures_answer_in_order(repository: NodeRepository) -> None:
    """One value per measure, in the order asked."""
    await _seed(repository)

    answers = await repository.aggregate(
        scope=ContentFilter.of(ALICE),
        resolved=_resolved(),
        measures=[CASES[8][1], CASES[0][1], CASES[10][1]],
    )

    assert [a.value for a in answers] == [13, 10, 2]


async def test_no_measures_ask_nothing(repository: NodeRepository) -> None:
    """An empty list of measures is an empty list of answers."""
    await _seed(repository)

    assert (
        await repository.aggregate(
            scope=ContentFilter.of(ALICE), resolved=_resolved(), measures=[]
        )
        == []
    )

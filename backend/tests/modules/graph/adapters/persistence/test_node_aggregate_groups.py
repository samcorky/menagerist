"""Grouped aggregates give the same answers in memory and in Postgres.

The in-memory evaluator is the reference. The data includes values of the wrong
shape (a number where a choice goes, a yes/no that is text), which both put in the
unset group, and items in several groups (tags, multiple choice).
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.node_repository import (
    SqlAlchemyNodeRepository,
)
from app.modules.graph.domain.aggregate import (
    CurrencyValue,
    GroupBy,
    GroupValue,
    Measure,
    MeasureSource,
    MeasureValue,
    ResolvedGroup,
    ResolvedMeasure,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import Query, ResolvedQuery
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=801)
BOB = uuid.UUID(int=802)


def _gbp(value: float) -> dict[str, Any]:
    return {"value": value, "currency": "GBP"}


# (type, tags, attributes)
_DATA: list[tuple[str | None, list[str], dict[str, Any]]] = [
    (
        "film",
        ["a", "b"],
        {
            "price": _gbp(10),
            "format": "dvd",
            "genres": ["drama", "scifi"],
            "owned": True,
        },
    ),
    (
        "film",
        ["a"],
        {"price": _gbp(5), "format": "dvd", "genres": ["drama"], "owned": False},
    ),
    (
        "film",
        [],
        {
            "price": {"value": 3, "currency": "USD"},
            "format": "Dvd",
            "genres": [],
            "owned": "yes",
        },
    ),
    ("film", ["b"], {"price": _gbp(2), "format": 5, "genres": ["scifi", "scifi"]}),
    ("subfilm", ["a"], {"price": _gbp(1)}),
    ("book", [], {"format": "dvd"}),
    (None, ["a"], {}),
]

FILMS = ("film", "subfilm")
ITEMS = ResolvedMeasure(measure=Measure(fn="count"), kind=None, sources=())
SUM_PRICE = ResolvedMeasure(
    measure=Measure(fn="sum", type="film", key="price"),
    kind="money",
    sources=(MeasureSource(types=FILMS, key="price"),),
)
COUNT_PRICE = ResolvedMeasure(
    measure=Measure(fn="count", type="film", key="price"),
    kind="money",
    sources=(MeasureSource(types=FILMS, key="price"),),
)


def _group(by: str, kind: str | None = None, key: str | None = None) -> ResolvedGroup:
    return ResolvedGroup(
        group=GroupBy(by=by, type="film" if key else None, key=key),  # type: ignore[arg-type]
        kind=kind,
        sources=(MeasureSource(types=FILMS, key=key),) if key else (),
    )


def _money(*pairs: tuple[str, float]) -> MeasureValue:
    return MeasureValue(
        currencies=tuple(CurrencyValue(currency=c, value=v) for c, v in pairs)
    )


def _by_key(groups: list[GroupValue]) -> dict[str | None, GroupValue]:
    return {g.key: g for g in groups}


CASES: list[tuple[str, ResolvedGroup, dict[str | None, tuple[int, MeasureValue]]]] = [
    (
        "by type, untyped is unset",
        _group("type"),
        {
            "film": (4, _money(("GBP", 17), ("USD", 3))),
            "subfilm": (1, _money(("GBP", 1))),
            "book": (1, MeasureValue()),
            None: (1, MeasureValue()),
        },
    ),
    (
        "by tag, an item is in each of its tags and none is unset",
        _group("tag"),
        {
            "a": (4, _money(("GBP", 16))),
            "b": (2, _money(("GBP", 12))),
            None: (2, _money(("USD", 3))),
        },
    ),
    (
        "by choice, a wrong shape and a type without the field are unset",
        _group("field", "choice", "format"),
        {
            "dvd": (2, _money(("GBP", 15))),
            "Dvd": (1, _money(("USD", 3))),
            None: (4, _money(("GBP", 3))),
        },
    ),
    (
        "by multiple choice, an item is in each choice once",
        _group("field", "multichoice", "genres"),
        {
            "drama": (2, _money(("GBP", 15))),
            "scifi": (2, _money(("GBP", 12))),
            None: (4, _money(("GBP", 1), ("USD", 3))),
        },
    ),
    (
        "by yes/no",
        _group("field", "boolean", "owned"),
        {
            "true": (1, _money(("GBP", 10))),
            "false": (1, _money(("GBP", 5))),
            None: (5, _money(("GBP", 3), ("USD", 3))),
        },
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
    for n, (type_slug, tags, attributes) in enumerate(_DATA):
        await repo.add(
            Node.create(
                owner_id=ALICE,
                name=f"Item {n}",
                type=type_slug,
                tags=tags,
                attributes=attributes,
            )
        )
    await repo.add(
        Node.create(
            owner_id=BOB,
            name="Theirs",
            type="film",
            tags=["a"],
            attributes={"price": _gbp(999), "format": "dvd"},
        )
    )
    return repo


@pytest.mark.parametrize(
    ("group", "expected"), [c[1:] for c in CASES], ids=[c[0] for c in CASES]
)
async def test_groups(
    repository: NodeRepository,
    group: ResolvedGroup,
    expected: dict[str | None, tuple[int, MeasureValue]],
) -> None:
    """Each group's size and total agree in both adapters, Bob's items left out."""
    await _seed(repository)

    groups = await repository.aggregate_groups(
        scope=ContentFilter.of(ALICE),
        resolved=_resolved(),
        group=group,
        measures=[SUM_PRICE],
    )

    found = _by_key(groups)
    assert {k: (g.count, g.values[0]) for k, g in found.items()} == expected


async def test_a_measure_with_nothing_to_read_is_empty_in_each_group(
    repository: NodeRepository,
) -> None:
    """A group where no item has a value still appears, with an empty answer."""
    await _seed(repository)

    groups = await repository.aggregate_groups(
        scope=ContentFilter.of(ALICE),
        resolved=_resolved(),
        group=_group("type"),
        measures=[ITEMS, COUNT_PRICE],
    )

    book = _by_key(groups)["book"]
    assert book.values == (MeasureValue(value=1), MeasureValue(value=0))


async def test_items_outside_the_shown_groups_count_once(
    repository: NodeRepository,
) -> None:
    """An item in two hidden groups is counted, and totalled, once."""
    await _seed(repository)

    rest = await repository.aggregate_outside_groups(
        scope=ContentFilter.of(ALICE),
        resolved=_resolved(),
        group=_group("tag"),
        measures=[ITEMS, SUM_PRICE],
        shown={"b"},
    )

    # Items 0, 1, 4 and 6 are in the hidden `a`; items 2 and 5 are in the hidden
    # unset group. Item 3 is only in `b`, which is shown.
    assert rest.key is None
    assert rest.count == 6
    assert rest.values[0] == MeasureValue(value=6)
    assert rest.values[1] == MeasureValue(
        currencies=(
            CurrencyValue(currency="GBP", value=16),
            CurrencyValue(currency="USD", value=3),
        )
    )


async def test_the_unset_group_can_be_shown(repository: NodeRepository) -> None:
    """With the unset group shown, only the named groups are left outside."""
    await _seed(repository)

    rest = await repository.aggregate_outside_groups(
        scope=ContentFilter.of(ALICE),
        resolved=_resolved(),
        group=_group("tag"),
        measures=[ITEMS],
        shown={None, "a"},
    )

    assert rest.count == 2  # items 0 and 3, the only ones in the hidden `b`


async def test_nothing_matching_has_no_groups(repository: NodeRepository) -> None:
    """With no items there are no groups, not an empty unset group."""
    assert (
        await repository.aggregate_groups(
            scope=ContentFilter.of(ALICE),
            resolved=_resolved(),
            group=_group("type"),
            measures=[ITEMS],
        )
        == []
    )

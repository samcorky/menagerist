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
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import Cursor, ResolvedQuery, parse_query
from app.shared_kernel.access_scope import AccessScope

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

ALICE = uuid.UUID(int=201)
BOB = uuid.UUID(int=202)
TODAY = date(2026, 10, 14)

SCHEMAS: dict[str, dict[str, Any]] = {
    "film": {
        "type": "object",
        "properties": {
            "year": {"type": "string", "x-menagerist": {"kind": "partialdate"}},
            "runtime": {"type": "number", "x-menagerist": {"kind": "duration"}},
            "rating": {"type": "number", "x-menagerist": {"kind": "rating"}},
            "seen": {"type": "boolean"},
            "genres": {
                "type": "array",
                "items": {"type": "string", "enum": ["scifi", "horror", "drama"]},
            },
            "director": {"type": "string"},
            "notes": {"type": "string"},
        },
    },
    "part": {
        "type": "object",
        "properties": {
            "stock": {"type": "number"},
            "reorder_at": {"type": "number"},
            "price": {"type": "object", "x-menagerist": {"kind": "money"}},
            "steps": {"type": "array", "x-menagerist": {"kind": "checklist"}},
            "bom": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ref": {"type": "string"},
                        "qty": {"type": "number"},
                    },
                },
                "x-menagerist": {"kind": "group"},
            },
        },
    },
}

_DATA: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = [
    (
        "Alien",
        "film",
        {
            "year": "1979",
            "runtime": 7020,
            "rating": 5,
            "seen": True,
            "genres": ["scifi", "horror"],
        },
        {"tags": ["classic"], "favourite": True},
    ),
    (
        "Blade Runner",
        "film",
        {
            "year": "1982-06",
            "runtime": 7020,
            "rating": 4,
            "seen": False,
            "genres": ["scifi"],
        },
        {},
    ),
    (
        "Casablanca",
        "film",
        {
            "year": "1942",
            "runtime": 6120,
            "rating": 5,
            "seen": True,
            "genres": ["drama"],
        },
        {"tags": ["classic"]},
    ),
    (
        "Café Society",
        "film",
        {"year": "2016-05-13", "director": "Woody Allen", "notes": "50% off_day"},
        {},
    ),
    ("Bad data", "film", {"year": 1999, "rating": "abc", "runtime": "long"}, {}),
    (
        "Resistor",
        "part",
        {
            "stock": 3,
            "reorder_at": 10,
            "price": {"value": 0.1, "currency": "GBP"},
            "steps": [{"text": "a", "done": True}],
            "bom": [{"ref": "R1", "qty": 2}, {"ref": ""}],
        },
        {},
    ),
    (
        "Capacitor",
        "part",
        {
            "stock": 50,
            "reorder_at": 10,
            "price": {"value": 0.3, "currency": "USD"},
            "steps": [{"text": "a", "done": True}, {"text": "b", "done": False}],
        },
        {},
    ),
]


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repository(request: pytest.FixtureRequest) -> NodeRepository:
    """The same scenarios run against both adapters (empty until `_seed`)."""
    if request.param == "in_memory":
        return InMemoryNodeRepository()
    return SqlAlchemyNodeRepository(request.getfixturevalue("db_session"))


async def _seed(repo: NodeRepository) -> NodeRepository:
    """Add the shared items: five films and two parts for Alice, one film for Bob."""
    for name, type_slug, attributes, extra in _DATA:
        node = Node.create(
            owner_id=ALICE, name=name, type=type_slug, attributes=attributes
        )
        node.tags = extra.get("tags", [])
        node.favourite = extra.get("favourite", False)
        await repo.add(node)
    await repo.add(
        Node.create(owner_id=BOB, name="Secret", type="film", attributes={"rating": 5})
    )
    return repo


def _resolve(raw: dict[str, Any]) -> ResolvedQuery:
    query = parse_query(raw)
    resolution = resolve_fields(query, SCHEMAS)
    return ResolvedQuery(
        query=query, field_kinds=resolution.kinds, search_exclusions={}, today=TODAY
    )


def _where(*children: dict[str, Any], op: str = "and", **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"v": 1, "where": {"op": op, "children": list(children)}, **extra}


def _f(
    type_: str,
    key: str,
    op: str,
    value: Any = None,  # noqa: ANN401
    **extra: Any,  # noqa: ANN401
) -> dict[str, Any]:
    cond: dict[str, Any] = {
        "kind": "field",
        "type": type_,
        "key": key,
        "op": op,
        **extra,
    }
    if value is not None:
        cond["value"] = value
    return cond


async def _names(
    repo: NodeRepository, raw: dict[str, Any], scope: AccessScope | None = None
) -> list[str]:
    hits = await repo.search(
        scope=scope or AccessScope.of(ALICE),
        resolved=_resolve(raw),
        after=None,
        limit=100,
    )
    return [hit.node.name for hit in hits]


_FILM = {"kind": "type", "in": ["film"]}

CASES: list[tuple[str, dict[str, Any], set[str]]] = [
    (
        "rating at least 4",
        _where(_f("film", "rating", ">=", 4)),
        {"Alien", "Blade Runner", "Casablanca"},
    ),
    (
        "not rating 4+ among films includes missing and wrong-typed",
        _where(_FILM, {"op": "not", "children": [_f("film", "rating", ">=", 4)]}),
        {"Café Society", "Bad data"},
    ),
    (
        "partial date year equals",
        _where(_f("film", "year", "=", "1982")),
        {"Blade Runner"},
    ),
    (
        "partial date between decades",
        _where(_f("film", "year", "between", ["1980", "1989"])),
        {"Blade Runner"},
    ),
    (
        "partial date at or after a month",
        _where(_f("film", "year", ">=", "2016-05")),
        {"Café Society"},
    ),
    (
        "field reference",
        _where(_f("part", "stock", "<=", {"ref": "reorder_at"})),
        {"Resistor"},
    ),
    (
        "multichoice has one",
        _where(_f("film", "genres", "has", "scifi")),
        {"Alien", "Blade Runner"},
    ),
    (
        "multichoice has all",
        _where(_f("film", "genres", "has", ["scifi", "horror"])),
        {"Alien"},
    ),
    (
        "money matches only its currency",
        _where(_f("part", "price", ">=", {"value": 0.05, "currency": "GBP"})),
        {"Resistor"},
    ),
    (
        "text is accent-insensitive",
        _where({"kind": "text", "q": "cafe"}),
        {"Café Society"},
    ),
    (
        "text treats % and _ literally",
        _where({"kind": "text", "q": "50% off_day"}),
        {"Café Society"},
    ),
    (
        "text does not treat _ as a wildcard",
        _where({"kind": "text", "q": "off_d_y"}),
        set(),
    ),
    (
        "tag any",
        _where({"kind": "tag", "mode": "any", "tags": ["classic"]}),
        {"Alien", "Casablanca"},
    ),
    (
        "tag none",
        _where(_FILM, {"kind": "tag", "mode": "none", "tags": ["classic"]}),
        {"Blade Runner", "Café Society", "Bad data"},
    ),
    ("favourite", _where({"kind": "favourite", "value": True}), {"Alien"}),
    (
        "or across types",
        _where(_f("film", "rating", "=", 5), _f("part", "stock", "<", 5), op="or"),
        {"Alien", "Casablanca", "Resistor"},
    ),
    (
        "not equal is scoped to the named type",
        _where(_f("film", "seen", "!=", True)),
        {"Blade Runner", "Café Society", "Bad data"},
    ),
    (
        "table column not empty",
        _where(_f("part", "bom", "not_empty", sub_key="ref")),
        {"Resistor"},
    ),
    (
        "table column empty is the complement within the type",
        _where(_f("part", "bom", "empty", sub_key="ref")),
        {"Capacitor"},
    ),
    (
        "table column not equal is not any row equals",
        _where(_f("part", "bom", "!=", "R1", sub_key="ref")),
        {"Capacitor"},
    ),
    ("empty means missing", _where(_f("film", "rating", "empty")), {"Café Society"}),
    ("not empty", _where(_f("film", "director", "not_empty")), {"Café Society"}),
    ("boolean", _where(_f("film", "seen", "=", True)), {"Alien", "Casablanca"}),
    (
        "boolean not equal includes missing",
        _where(_FILM, _f("film", "seen", "!=", True)),
        {"Blade Runner", "Café Society", "Bad data"},
    ),
    ("duration at most", _where(_f("film", "runtime", "<=", 6500)), {"Casablanca"}),
    (
        "wrong-typed value never matches or errors",
        _where(_f("film", "runtime", ">", 0)),
        {"Alien", "Blade Runner", "Casablanca"},
    ),
    ("checklist incomplete", _where(_f("part", "steps", "incomplete")), {"Capacitor"}),
    ("checklist complete", _where(_f("part", "steps", "complete")), {"Resistor"}),
    (
        "created within the last day",
        _where({"kind": "date", "on": "created", "op": ">=", "value": {"rel": "-1d"}}),
        {
            "Alien",
            "Blade Runner",
            "Casablanca",
            "Café Society",
            "Bad data",
            "Resistor",
            "Capacitor",
        },
    ),
    (
        "created before yesterday",
        _where({"kind": "date", "on": "created", "op": "<", "value": {"rel": "-1d"}}),
        set(),
    ),
    (
        "or group cannot reach another user's items",
        _where(_FILM, {"kind": "text", "q": "secret"}, op="or"),
        {"Alien", "Blade Runner", "Casablanca", "Café Society", "Bad data"},
    ),
    ("stale field matches nothing", _where(_f("film", "gone", "=", "x")), set()),
    (
        "not of a stale field matches everything",
        {"v": 1, "where": {"op": "not", "children": [_f("film", "gone", "=", "x")]}},
        {n for n, *_ in _DATA},
    ),
]


@pytest.mark.parametrize(("label", "raw", "expected"), CASES, ids=[c[0] for c in CASES])
async def test_scenario(
    repository: NodeRepository, label: str, raw: dict[str, Any], expected: set[str]
) -> None:
    """Scenario."""
    del label
    await _seed(repository)
    assert set(await _names(repository, raw)) == expected
    resolved = _resolve(raw)
    assert await repository.search_count(
        scope=AccessScope.of(ALICE), resolved=resolved
    ) == len(expected)


async def test_no_where_returns_everything_in_creation_order(
    repository: NodeRepository,
) -> None:
    """No where returns everything in creation order."""
    await _seed(repository)
    assert await _names(repository, {"v": 1, "where": None}) == [n for n, *_ in _DATA]


async def test_everyone_scope_sees_every_owner(repository: NodeRepository) -> None:
    """Everyone scope sees every owner."""
    await _seed(repository)
    assert "Secret" in await _names(
        repository, {"v": 1, "where": None}, AccessScope.everyone()
    )


async def test_sort_by_field_puts_nulls_last_and_breaks_ties_by_creation(
    repository: NodeRepository,
) -> None:
    """Sort by field puts nulls last and breaks ties by creation."""
    await _seed(repository)
    raw = _where(
        _FILM, sort=[{"by": "field", "type": "film", "key": "rating", "dir": "desc"}]
    )
    assert await _names(repository, raw) == [
        "Alien",
        "Casablanca",
        "Blade Runner",
        "Café Society",
        "Bad data",
    ]


async def test_sort_by_name_ignores_case_and_accents(
    repository: NodeRepository,
) -> None:
    """Sort by name ignores case and accents."""
    await _seed(repository)
    names = await _names(repository, _where(_FILM, sort=[{"by": "name"}]))
    assert names == ["Alien", "Bad data", "Blade Runner", "Café Society", "Casablanca"]


@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_paging_visits_every_item_once(
    repository: NodeRepository, direction: str
) -> None:
    """Paging visits every item once."""
    await _seed(repository)
    raw = _where(
        _FILM, sort=[{"by": "field", "type": "film", "key": "rating", "dir": direction}]
    )
    resolved = _resolve(raw)
    seen: list[str] = []
    after: Cursor | None = None
    while True:
        hits = await repository.search(
            scope=AccessScope.of(ALICE), resolved=resolved, after=after, limit=2
        )
        seen += [hit.node.name for hit in hits]
        if len(hits) < 2:
            break
        last = hits[-1]
        after = Cursor(sort_values=last.sort_values, id=last.node.id)
    assert sorted(seen) == sorted(
        ["Alien", "Blade Runner", "Casablanca", "Café Society", "Bad data"]
    )
    assert len(seen) == len(set(seen))


async def test_paging_continues_after_the_cursor_row_is_deleted(
    repository: NodeRepository,
) -> None:
    """Paging continues after the cursor row is deleted."""
    await _seed(repository)
    raw = _where(_FILM, sort=[{"by": "name"}])
    resolved = _resolve(raw)
    first = await repository.search(
        scope=AccessScope.of(ALICE), resolved=resolved, after=None, limit=2
    )
    victim = first[-1].node
    victim.soft_delete()
    await repository.save(victim)
    cursor = Cursor(sort_values=first[-1].sort_values, id=victim.id)
    rest = await repository.search(
        scope=AccessScope.of(ALICE), resolved=resolved, after=cursor, limit=10
    )
    assert [hit.node.name for hit in rest] == [
        "Blade Runner",
        "Café Society",
        "Casablanca",
    ]


async def test_not_includes_items_whose_values_are_null(
    repository: NodeRepository,
) -> None:
    """NOT keeps an untyped item and an item with no description (SQL NULLs)."""
    await repository.add(Node.create(owner_id=ALICE, name="Loose"))
    await repository.add(Node.create(owner_id=ALICE, name="Heat", type="film"))
    not_film = {"op": "not", "children": [_FILM]}
    not_text = {"op": "not", "children": [{"kind": "text", "q": "zzz"}]}
    assert await _names(repository, {"v": 1, "where": not_film}) == ["Loose"]
    assert set(await _names(repository, {"v": 1, "where": not_text})) == {
        "Loose",
        "Heat",
    }

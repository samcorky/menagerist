import uuid
from datetime import UTC, date, datetime
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
            "format": {"type": "string", "enum": ["VHS", "DVD", "vhs"]},
            "notes": {"type": "string"},
        },
    },
    "part": {
        "type": "object",
        "properties": {
            "stock": {"type": "number"},
            "reorder_at": {"type": "number"},
            "old_reorder": {"type": "number", "x-menagerist": {"archived": True}},
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
    "game": {
        "type": "object",
        "properties": {
            "weight": {"type": "number", "x-menagerist": {"kind": "number"}},
        },
    },
}


def _overlay(**fields: dict[str, Any]) -> dict[str, Any]:
    """A per-item overlay: each field is its `x-menagerist` metadata."""
    return {
        "type": "object",
        "properties": {key: {"x-menagerist": meta} for key, meta in fields.items()},
    }


_SIGNED = {"extra_schema": _overlay(signed={"kind": "boolean"})}

_DATA: list[tuple[str, str | None, dict[str, Any], dict[str, Any]]] = [
    (
        "Alien",
        "film",
        {
            "year": "1979",
            "runtime": 7020,
            "rating": 5,
            "seen": True,
            "genres": ["scifi", "horror"],
            "format": "VHS",
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
            "format": "DVD",
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
            "format": "vhs",
        },
        {"tags": ["classic"]},
    ),
    (
        "Café Society",
        "film",
        {"year": "2016-05-13", "director": "Woody Allen", "notes": "50% off_day"},
        {},
    ),
    (
        "Bad data",
        "film",
        {"year": 1999, "rating": "abc", "runtime": "long", "format": 7},
        {},
    ),
    (
        "Resistor",
        "part",
        {
            "stock": 3,
            "reorder_at": 10,
            "old_reorder": 10,
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
    ("Signed copy", None, {"signed": True}, _SIGNED),
    ("Unsigned copy", None, {"signed": False}, _SIGNED),
    ("Undecided", None, {}, _SIGNED),
    ("Rogue", None, {"signed": True, "size": 20}, {}),
    (
        "Notes only",
        None,
        {"signed": "yes"},
        {"extra_schema": _overlay(signed={"kind": "text"})},
    ),
    (
        "Big box",
        None,
        {"size": 12},
        {"extra_schema": _overlay(size={"kind": "number"})},
    ),
    (
        "Small label",
        None,
        {"size": "large"},
        {"extra_schema": _overlay(size={"kind": "text"})},
    ),
    ("Blank label", None, {}, {"extra_schema": _overlay(size={"kind": "text"})}),
    (
        "Worn",
        None,
        {"condition": "poor"},
        {"extra_schema": _overlay(condition={"kind": "text", "archived": True})},
    ),
    ("Chess", "game", {"weight": 5}, {}),
    (
        "Reel",
        "tape",
        {"weight": 5},
        {"extra_schema": _overlay(weight={"kind": "number"})},
    ),
]


# Descriptions for the description and name scenarios; others have none (NULL).
_DESCRIPTIONS: dict[str, str] = {
    "Alien": "Ripley fights a xenomorph, 100% tense_scene",
    "Blade Runner": "Crème brûlée replicants",
    "Casablanca": "  \t\n ",
    "Bad data": "",
}


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
            owner_id=ALICE,
            name=name,
            type=type_slug,
            attributes=attributes,
            extra_schema=extra.get("extra_schema"),
        )
        node.tags = extra.get("tags", [])
        node.favourite = extra.get("favourite", False)
        node.description = _DESCRIPTIONS.get(name)
        await repo.add(node)
    await repo.add(
        Node.create(
            owner_id=BOB,
            name="Secret",
            description="xenomorph secret",
            type="film",
            attributes={"rating": 5},
        )
    )
    return repo


def _resolve(raw: dict[str, Any]) -> ResolvedQuery:
    query = parse_query(raw)
    resolution = resolve_fields(query, SCHEMAS)
    return ResolvedQuery(
        query=query,
        field_kinds=resolution.kinds,
        search_exclusions={},
        today=TODAY,
        stale=resolution.stale,
    )


def _p(
    field_kind: str,
    key: str,
    op: str,
    value: Any = None,  # noqa: ANN401
) -> dict[str, Any]:
    """A per-item field condition."""
    cond: dict[str, Any] = {
        "kind": "field",
        "field_kind": field_kind,
        "key": key,
        "op": op,
    }
    if value is not None:
        cond["value"] = value
    return cond


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
_FILMS = {"Alien", "Blade Runner", "Casablanca", "Café Society", "Bad data"}
_ITEMS = {
    "Signed copy",
    "Unsigned copy",
    "Undecided",
    "Rogue",
    "Notes only",
    "Big box",
    "Small label",
    "Blank label",
    "Worn",
    "Chess",
    "Reel",
}

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
        "description ~ finds words in the description only",
        _where({"kind": "description", "op": "~", "value": "xenomorph"}),
        {"Alien"},
    ),
    (
        "description ~ is case- and accent-insensitive",
        _where({"kind": "description", "op": "~", "value": "CREME BRULEE"}),
        {"Blade Runner"},
    ),
    (
        "description ~ folds accents in the query too",
        _where({"kind": "description", "op": "~", "value": "crème"}),
        {"Blade Runner"},
    ),
    (
        "description ~ treats % literally",
        _where({"kind": "description", "op": "~", "value": "100%"}),
        {"Alien"},
    ),
    (
        "description ~ treats a lone % as a character, not a wildcard",
        _where({"kind": "description", "op": "~", "value": "%"}),
        {"Alien"},
    ),
    (
        "description ~ treats _ literally",
        _where({"kind": "description", "op": "~", "value": "tense_scene"}),
        {"Alien"},
    ),
    (
        "description ~ does not treat _ as a wildcard",
        _where({"kind": "description", "op": "~", "value": "tens_ scene"}),
        set(),
    ),
    (
        "description ~ does not match the name",
        _where({"kind": "description", "op": "~", "value": "Casablanca"}),
        set(),
    ),
    (
        "description ~ never returns another owner's item",
        _where({"kind": "description", "op": "~", "value": "secret"}),
        set(),
    ),
    (
        "description ~ inside not keeps items without one",
        _where(
            {
                "op": "not",
                "children": [{"kind": "description", "op": "~", "value": "xeno"}],
            }
        ),
        {n for n, *_ in _DATA} - {"Alien"},
    ),
    (
        "description empty is NULL, empty and whitespace-only",
        _where({"kind": "description", "op": "empty"}),
        {n for n, *_ in _DATA} - {"Alien", "Blade Runner"},
    ),
    (
        "description not_empty needs real text",
        _where({"kind": "description", "op": "not_empty"}),
        {"Alien", "Blade Runner"},
    ),
    (
        "description empty combines with a type",
        _where(_FILM, {"kind": "description", "op": "empty"}),
        {"Casablanca", "Café Society", "Bad data"},
    ),
    (
        "name ~ finds words in the name only",
        _where({"kind": "name", "op": "~", "value": "blade"}),
        {"Blade Runner"},
    ),
    (
        "name ~ is case- and accent-insensitive",
        _where({"kind": "name", "op": "~", "value": "CAFE soc"}),
        {"Café Society"},
    ),
    (
        "name ~ does not match the description",
        _where({"kind": "name", "op": "~", "value": "xenomorph"}),
        set(),
    ),
    (
        "name ~ treats % and _ literally",
        _where({"kind": "name", "op": "~", "value": "%"}),
        set(),
    ),
    (
        "name ~ does not treat _ as a wildcard",
        _where({"kind": "name", "op": "~", "value": "A_ien"}),
        set(),
    ),
    (
        "name = is a whole-name match ignoring case and accents",
        _where({"kind": "name", "op": "=", "value": "CAFE SOCIETY"}),
        {"Café Society"},
    ),
    (
        "name = folds accents in the query too",
        _where({"kind": "name", "op": "=", "value": "café society"}),
        {"Café Society"},
    ),
    (
        "name = does not match part of a name",
        _where({"kind": "name", "op": "=", "value": "Alie"}),
        set(),
    ),
    (
        "name = treats % literally",
        _where({"kind": "name", "op": "=", "value": "%"}),
        set(),
    ),
    (
        "name = inside not matches everything else",
        _where(
            {"op": "not", "children": [{"kind": "name", "op": "=", "value": "alien"}]}
        ),
        {n for n, *_ in _DATA} - {"Alien"},
    ),
    (
        "name = never returns another owner's item",
        _where({"kind": "name", "op": "=", "value": "secret"}),
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
    (
        "not in is scoped to the named type and includes missing values",
        _where(_f("film", "director", "not_in", ["Ridley Scott"])),
        _FILMS,
    ),
    (
        "not in folds case and accents for text",
        _where(_f("film", "director", "not_in", ["WOODY ÁLLEN", "x"])),
        _FILMS - {"Café Society"},
    ),
    (
        "not in compares a choice exactly and keeps wrong-typed values",
        _where(_f("film", "format", "not_in", ["VHS"])),
        {"Blade Runner", "Casablanca", "Café Society", "Bad data"},
    ),
    (
        "not in with every value listed leaves only the missing and wrong-typed",
        _where(_f("film", "format", "not_in", ["VHS", "DVD", "vhs"])),
        {"Café Society", "Bad data"},
    ),
    (
        "not of not in is in, or any other type",
        {
            "v": 1,
            "where": {
                "op": "not",
                "children": [_f("film", "director", "not_in", ["woody allen"])],
            },
        },
        {"Café Society", "Resistor", "Capacitor"} | _ITEMS,
    ),
    (
        "not of not in within the type equals in",
        _where(
            _FILM,
            {"op": "not", "children": [_f("film", "format", "not_in", ["VHS", "DVD"])]},
        ),
        {"Alien", "Blade Runner"},
    ),
    (
        "not in beside its complement matches nothing",
        _where(
            _f("film", "format", "in", ["VHS"]),
            _f("film", "format", "not_in", ["VHS"]),
        ),
        set(),
    ),
    (
        "table column not in is no row in the list",
        _where(_f("part", "bom", "not_in", ["r1", "x"], sub_key="ref")),
        {"Capacitor"},
    ),
    (
        "table column not in keeps items whose rows hold other values",
        _where(_f("part", "bom", "not_in", ["x"], sub_key="ref")),
        {"Resistor", "Capacitor"},
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
        }
        | _ITEMS,
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
        "stale field matches nothing under not in",
        _where(_f("film", "gone", "not_in", ["x"])),
        set(),
    ),
    (
        "not of a stale not in matches everything",
        {
            "v": 1,
            "where": {"op": "not", "children": [_f("film", "gone", "not_in", ["x"])]},
        },
        {n for n, *_ in _DATA},
    ),
    (
        "stale reference matches nothing beside a live condition on its field",
        _where(
            _f("part", "stock", "<=", {"ref": "old_reorder"}),
            _f("part", "stock", "not_empty"),
        ),
        set(),
    ),
    (
        "per-item boolean equals, ignoring items without that overlay",
        _where(_p("boolean", "signed", "=", True)),
        {"Signed copy"},
    ),
    (
        "per-item not equal is scoped to items declaring the field",
        _where(_p("boolean", "signed", "!=", True)),
        {"Unsigned copy", "Undecided"},
    ),
    (
        "not of a per-item condition is plain negation",
        {
            "v": 1,
            "where": {"op": "not", "children": [_p("boolean", "signed", "=", True)]},
        },
        {n for n, *_ in _DATA} - {"Signed copy"},
    ),
    (
        "per-item number matches only the number item",
        _where(_p("number", "size", ">=", 10)),
        {"Big box"},
    ),
    (
        "per-item text matches only the text item",
        _where(_p("text", "size", "=", "LARGE")),
        {"Small label"},
    ),
    (
        "per-item empty is scoped to items declaring the field",
        _where(_p("text", "size", "empty")),
        {"Blank label"},
    ),
    (
        "per-item not empty is scoped to items declaring the field",
        _where(_p("text", "size", "not_empty")),
        {"Small label"},
    ),
    (
        "per-item not in is scoped and includes missing values",
        _where(_p("text", "size", "not_in", ["x"])),
        {"Small label", "Blank label"},
    ),
    (
        "per-item not in excludes the listed value",
        _where(_p("text", "size", "not_in", ["large"])),
        {"Blank label"},
    ),
    (
        "archived per-item field matches nothing",
        _where(_p("text", "condition", "=", "poor")),
        set(),
    ),
    (
        "archived per-item field matches nothing under not equal",
        _where(_p("text", "condition", "!=", "good")),
        set(),
    ),
    (
        "per-item key equal to a type key matches only the item's own field",
        _where(_p("number", "weight", "=", 5)),
        {"Reel"},
    ),
    (
        "type field still matches only its type",
        _where(_f("game", "weight", "=", 5)),
        {"Chess"},
    ),
    (
        "per-item not equal ignores the type's field of the same name",
        _where(_p("number", "weight", "!=", 9)),
        {"Reel"},
    ),
    (
        "per-item inside or beside a type condition",
        _where(
            _p("boolean", "signed", "=", True), _f("film", "rating", "=", 5), op="or"
        ),
        {"Signed copy", "Alien", "Casablanca"},
    ),
    (
        "per-item kind that nobody declares matches nothing",
        _where(_p("money", "signed", "not_empty")),
        set(),
    ),
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


@pytest.mark.parametrize(
    ("raw", "limit", "expected"),
    [
        (_where(_f("film", "rating", ">=", 4)), 2, 2),
        (_where(_f("film", "rating", ">=", 4)), 3, 3),
        (_where(_f("film", "rating", ">=", 4)), 4, 3),
        (_where(_f("film", "rating", ">=", 4)), None, 3),
        ({"v": 1, "where": None}, 5, 5),
        ({"v": 1, "where": None}, None, len(_DATA)),
    ],
    ids=["below", "exact", "above", "unlimited", "capped-all", "uncapped-all"],
)
async def test_search_count_limit_caps_the_count(
    repository: NodeRepository, raw: dict[str, Any], limit: int | None, expected: int
) -> None:
    """A count limit bounds the result without changing smaller counts."""
    await _seed(repository)
    count = await repository.search_count(
        scope=AccessScope.of(ALICE), resolved=_resolve(raw), limit=limit
    )
    assert count == expected


@pytest.mark.parametrize("by", ["name", "created"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_paging_by_name_or_time_visits_every_item_once(
    repository: NodeRepository, by: str, direction: str
) -> None:
    """Paging by a never-null key continues exactly where the cursor left off."""
    await _seed(repository)
    resolved = _resolve({"v": 1, "where": None, "sort": [{"by": by, "dir": direction}]})
    seen: list[str] = []
    after: Cursor | None = None
    while True:
        hits = await repository.search(
            scope=AccessScope.of(ALICE), resolved=resolved, after=after, limit=2
        )
        seen += [hit.node.name for hit in hits]
        if len(hits) < 2:
            break
        after = Cursor(sort_values=hits[-1].sort_values, id=hits[-1].node.id)
    assert sorted(seen) == sorted(n for n, *_ in _DATA)


@pytest.mark.parametrize("by", ["name", "created", "updated"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_paging_through_ties_in_the_first_key_matches_the_unpaged_order(
    repository: NodeRepository, by: str, direction: str
) -> None:
    """Pages over tied first-key values lose and repeat nothing, in order."""
    names = ["alpha", "Alpha", "ALPHA", "Álpha", "beta", "Beta", "BETA", "gamma"]
    for index, name in enumerate(names):
        node = Node.create(owner_id=ALICE, name=name, type="film")
        stamp = datetime(2026, 10, 1 + index // 3, tzinfo=UTC)
        node.created_at = stamp
        node.updated_at = stamp
        await repository.add(node)
    resolved = _resolve({"v": 1, "where": None, "sort": [{"by": by, "dir": direction}]})
    scope = AccessScope.of(ALICE)
    unpaged = await repository.search(
        scope=scope, resolved=resolved, after=None, limit=100
    )
    paged: list[uuid.UUID] = []
    after: Cursor | None = None
    while True:
        hits = await repository.search(
            scope=scope, resolved=resolved, after=after, limit=2
        )
        paged += [hit.node.id for hit in hits]
        if len(hits) < 2:
            break
        after = Cursor(sort_values=hits[-1].sort_values, id=hits[-1].node.id)
    assert paged == [hit.node.id for hit in unpaged]
    assert len(paged) == len(names)


_HUGE = 10**400


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (_where(_f("part", "stock", "<", 5)), ["Resistor"]),
        (_where(_f("part", "stock", ">=", 0)), ["Resistor", "Capacitor"]),
        (_where(_f("part", "stock", "between", [0, 100])), ["Resistor", "Capacitor"]),
        (
            _where(
                {"kind": "type", "in": ["part"]},
                {"op": "not", "children": [_f("part", "stock", ">=", 0)]},
            ),
            ["Overflow"],
        ),
        (
            _where(_f("part", "stock", ">=", {"ref": "reorder_at"})),
            ["Capacitor"],
        ),
        (
            _where(_f("part", "price", ">=", {"value": 0, "currency": "GBP"})),
            ["Resistor"],
        ),
        (
            _where(
                {"kind": "type", "in": ["part"]},
                sort=[{"by": "field", "type": "part", "key": "stock", "dir": "desc"}],
            ),
            ["Capacitor", "Resistor", "Overflow"],
        ),
        (
            _where(
                {"kind": "type", "in": ["part"]},
                sort=[{"by": "field", "type": "part", "key": "price"}],
            ),
            ["Resistor", "Capacitor", "Overflow"],
        ),
    ],
    ids=[
        "less than",
        "at least",
        "between",
        "not",
        "reference",
        "money",
        "number sort",
        "money sort",
    ],
)
async def test_number_beyond_float_range_is_treated_as_the_wrong_type(
    repository: NodeRepository, raw: dict[str, Any], expected: list[str]
) -> None:
    """One stored number too large for a float neither matches nor errors."""
    await _seed(repository)
    await repository.add(
        Node.create(
            owner_id=ALICE,
            name="Overflow",
            type="part",
            attributes={
                "stock": _HUGE,
                "reorder_at": -_HUGE,
                "price": {"value": _HUGE, "currency": "GBP"},
            },
        )
    )
    assert await _names(repository, raw) == expected


@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_not_in_leaves_sorting_and_paging_alone(
    repository: NodeRepository, direction: str
) -> None:
    """A not-in filter pages through the same order as the unpaged search."""
    await _seed(repository)
    raw = _where(
        _f("film", "format", "not_in", ["DVD"]),
        sort=[{"by": "field", "type": "film", "key": "rating", "dir": direction}],
    )
    resolved = _resolve(raw)
    scope = AccessScope.of(ALICE)
    unpaged = await repository.search(
        scope=scope, resolved=resolved, after=None, limit=100
    )
    names = [hit.node.name for hit in unpaged]
    rated = ["Alien", "Casablanca"]
    assert names == [*rated, "Café Society", "Bad data"]
    paged: list[str] = []
    after: Cursor | None = None
    while True:
        hits = await repository.search(
            scope=scope, resolved=resolved, after=after, limit=1
        )
        paged += [hit.node.name for hit in hits]
        if not hits:
            break
        after = Cursor(sort_values=hits[-1].sort_values, id=hits[-1].node.id)
    assert paged == names
    assert await repository.search_count(scope=scope, resolved=resolved) == 4

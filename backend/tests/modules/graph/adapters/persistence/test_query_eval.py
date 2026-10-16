"""Branches of the Python query evaluator the shared scenarios do not reach.

The repository-level cases also run against Postgres, so the SQL compiler is
held to the same answers.
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
from app.modules.graph.adapters.persistence.query_eval import is_after, sort_values
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import (
    Cursor,
    Query,
    ResolvedQuery,
    SearchHit,
    SortKey,
    parse_query,
)
from app.shared_kernel.access_scope import AccessScope

if TYPE_CHECKING:
    from app.modules.graph.ports.node_repository import NodeRepository

OWNER = uuid.UUID(int=301)
TODAY = date(2026, 10, 14)

SCHEMAS: dict[str, dict[str, Any]] = {
    "thing": {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "colour": {"type": "string", "enum": ["Red", "Blue"]},
            "count": {"type": "number", "x-menagerist": {"kind": "number"}},
            "limit": {"type": "number", "x-menagerist": {"kind": "number"}},
            "price": {"type": "object", "x-menagerist": {"kind": "money"}},
            "cap": {"type": "object", "x-menagerist": {"kind": "money"}},
            "bought": {"type": "string", "format": "date"},
            "due": {"type": "string", "format": "date"},
            "year": {"type": "string", "x-menagerist": {"kind": "partialdate"}},
            "parts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "qty": {"type": "number"},
                    },
                },
            },
        },
    }
}


def _node(name: str, **attributes: Any) -> Node:  # noqa: ANN401
    return Node.create(owner_id=OWNER, name=name, type="thing", attributes=attributes)


def _resolve(raw: dict[str, Any]) -> ResolvedQuery:
    query = parse_query(raw)
    kinds = resolve_fields(query, SCHEMAS).kinds
    return ResolvedQuery(
        query=query, field_kinds=kinds, search_exclusions={}, today=TODAY
    )


def _f(key: str, op: str, value: Any = None, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    cond: dict[str, Any] = {
        "kind": "field",
        "type": "thing",
        "key": key,
        "op": op,
        **extra,
    }
    if value is not None:
        cond["value"] = value
    return cond


@pytest.fixture(
    params=["in_memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def repository(request: pytest.FixtureRequest) -> NodeRepository:
    """An empty repository of each adapter."""
    if request.param == "in_memory":
        return InMemoryNodeRepository()
    return SqlAlchemyNodeRepository(request.getfixturevalue("db_session"))


async def _run(
    repo: NodeRepository, nodes: list[Node], *children: dict[str, Any], op: str = "and"
) -> set[str]:
    """Add any of `nodes` not yet stored, then search with the given children."""
    for node in nodes:
        if await repo.get(node.id, scope=AccessScope.of(OWNER)) is None:
            await repo.add(node)
    raw = {"v": 1, "where": {"op": op, "children": list(children)}}
    hits = await repo.search(
        scope=AccessScope.of(OWNER), resolved=_resolve(raw), after=None, limit=100
    )
    return {hit.node.name for hit in hits}


async def test_numeric_between_and_bool_is_not_a_number(
    repository: NodeRepository,
) -> None:
    """Numeric between and bool is not a number."""
    nodes = [_node("a", count=5), _node("b", count=12), _node("c", count=True)]
    assert await _run(repository, nodes, _f("count", "between", [1, 10])) == {"a"}


async def test_money_between_needs_the_same_currency(
    repository: NodeRepository,
) -> None:
    """Money between needs the same currency."""
    nodes = [
        _node("gbp", price={"value": 5, "currency": "GBP"}),
        _node("usd", price={"value": 5, "currency": "USD"}),
        _node("big", price={"value": 50, "currency": "GBP"}),
        _node("bad", price={"value": "x", "currency": "GBP"}),
        _node("text", price="5"),
    ]
    low = {"value": 1, "currency": "GBP"}
    high = {"value": 10, "currency": "GBP"}
    assert await _run(repository, nodes, _f("price", "between", [low, high])) == {"gbp"}


async def test_money_field_reference_uses_the_other_amount(
    repository: NodeRepository,
) -> None:
    """Money field reference uses the other amount."""
    nodes = [
        _node(
            "under",
            price={"value": 1, "currency": "GBP"},
            cap={"value": 5, "currency": "GBP"},
        ),
        _node(
            "over",
            price={"value": 9, "currency": "GBP"},
            cap={"value": 5, "currency": "GBP"},
        ),
        _node("no cap", price={"value": 1, "currency": "GBP"}),
    ]
    assert await _run(repository, nodes, _f("price", "<=", {"ref": "cap"})) == {"under"}


async def test_date_field_reference_and_between(repository: NodeRepository) -> None:
    """Date field reference and between."""
    nodes = [
        _node("early", bought="2020-01-01", due="2021-01-01"),
        _node("late", bought="2022-01-01", due="2021-01-01"),
        _node("no due", bought="2020-01-01"),
        _node("wrong", bought=5, due="2021-01-01"),
    ]
    assert await _run(repository, nodes, _f("bought", "<", {"ref": "due"})) == {"early"}
    assert await _run(
        repository, nodes, _f("bought", "between", ["2019-01-01", "2020-12-31"])
    ) == {
        "early",
        "no due",
    }


async def test_field_reference_to_a_wrong_typed_target_never_matches(
    repository: NodeRepository,
) -> None:
    """Field reference to a wrong typed target never matches."""
    nodes = [_node("a", count=1, limit="many")]
    assert await _run(repository, nodes, _f("count", "<", {"ref": "limit"})) == set()


async def test_partial_date_between_compares_to_each_bound_precision(
    repository: NodeRepository,
) -> None:
    """Partial date between compares to each bound precision."""
    nodes = [
        _node("a", year="1985-03-02"),
        _node("b", year="1990"),
        _node("c", year="1979"),
        _node("d", year=1985),
    ]
    assert await _run(
        repository, nodes, _f("year", "between", ["1980", "1989-12"])
    ) == {"a"}


async def test_choice_is_exact_and_text_folds(repository: NodeRepository) -> None:
    """Choice is exact and text folds."""
    nodes = [
        _node("red", colour="Red", label="Café"),
        _node("blue", colour="Blue", label="cafe au lait"),
        _node("num", colour=3, label=3),
    ]
    assert await _run(repository, nodes, _f("colour", "=", "Red")) == {"red"}
    assert await _run(repository, nodes, _f("colour", "=", "red")) == set()
    assert await _run(repository, nodes, _f("colour", "in", ["Red", "Blue"])) == {
        "red",
        "blue",
    }
    assert await _run(repository, nodes, _f("colour", "in", ["red"])) == set()
    assert await _run(repository, nodes, _f("label", "~", "CAFE")) == {"red", "blue"}
    assert await _run(repository, nodes, _f("label", "=", "cafe")) == {"red"}
    assert await _run(repository, nodes, _f("label", "in", ["CAFÉ", "x"])) == {"red"}
    assert await _run(repository, nodes, _f("colour", "not_in", ["red"])) == {
        "red",
        "blue",
        "num",
    }
    assert await _run(repository, nodes, _f("colour", "not_in", ["Red"])) == {
        "blue",
        "num",
    }
    assert await _run(repository, nodes, _f("label", "not_in", ["CAFÉ", "x"])) == {
        "blue",
        "num",
    }


async def test_table_columns_match_any_row(repository: NodeRepository) -> None:
    """Table columns match any row."""
    nodes = [
        _node("a", parts=[{"sku": "x1", "qty": 1}, {"sku": "y2", "qty": 9}]),
        _node("b", parts=[{"sku": "x1"}, "junk"]),
        _node("c", parts="not a list"),
        _node("d"),
    ]
    assert await _run(repository, nodes, _f("parts", "=", "y2", sub_key="sku")) == {"a"}
    assert await _run(repository, nodes, _f("parts", ">", 5, sub_key="qty")) == {"a"}
    assert await _run(repository, nodes, _f("parts", "empty", sub_key="qty")) == {
        "b",
        "c",
        "d",
    }
    assert await _run(repository, nodes, _f("parts", "not_empty", sub_key="qty")) == {
        "a"
    }
    # != is the negation of =, so rows without a match (or no table) qualify
    assert await _run(repository, nodes, _f("parts", "!=", "y2", sub_key="sku")) == {
        "b",
        "c",
        "d",
    }
    # not_in follows the same rule: no row holds a listed value
    assert await _run(
        repository, nodes, _f("parts", "not_in", ["Y2", "z"], sub_key="sku")
    ) == {"b", "c", "d"}


async def test_tag_all_and_updated_date_and_not_group(
    repository: NodeRepository,
) -> None:
    """Tag all and updated date and not group."""
    both = _node("both")
    both.tags = ["a", "b"]
    one = _node("one")
    one.tags = ["a"]
    assert await _run(
        repository, [both, one], {"kind": "tag", "mode": "all", "tags": ["a", "b"]}
    ) == {"both"}
    today = {"kind": "date", "on": "updated", "op": ">=", "value": {"rel": "-1d"}}
    assert await _run(repository, [both, one], today) == {"both", "one"}
    window = {
        "kind": "date",
        "on": "updated",
        "op": "between",
        "value": ["2000-01-01", "2000-12-31"],
    }
    assert await _run(repository, [both], window) == set()
    assert (
        await _run(repository, [both, one], {"op": "not", "children": [today]}) == set()
    )


def _sort_ctx(*keys: dict[str, Any]) -> ResolvedQuery:
    """Build the query directly: the parser caps sort keys at three."""
    query = Query(where=None, sort=tuple(SortKey(**key) for key in keys))
    kinds = resolve_fields(query, SCHEMAS).kinds
    return ResolvedQuery(
        query=query, field_kinds=kinds, search_exclusions={}, today=TODAY
    )


def test_sort_values_cover_every_key_kind() -> None:
    """Sort values cover every key kind."""
    node = _node(
        "Éclair",
        count=3,
        price={"value": 2, "currency": "GBP"},
        bought="2020-01-01",
        label="Ábc",
        year="1999",
    )
    keys = [
        {"by": "name"},
        {"by": "created"},
        {"by": "updated"},
        *(
            {"by": "field", "type": "thing", "key": k}
            for k in ("count", "price", "bought", "label", "year")
        ),
    ]
    values = sort_values(node, _sort_ctx(*keys))
    assert values == (
        "eclair",
        node.created_at.timestamp(),
        node.updated_at.timestamp(),
        3.0,
        2.0,
        "2020-01-01",
        "abc",
        "1999",
    )


def test_sort_values_are_none_for_stale_missing_or_wrong_typed_fields() -> None:
    """Sort values are none for stale missing or wrong typed fields."""
    node = _node("n", count="x", price="y", label=4)
    keys = [
        {"by": "field", "type": "thing", "key": k}
        for k in ("count", "price", "label", "gone")
    ]
    assert sort_values(node, _sort_ctx(*keys)) == (None, None, None, None)
    other = Node.create(owner_id=OWNER, name="o", type="other")
    one = _sort_ctx({"by": "field", "type": "thing", "key": "count"})
    assert sort_values(other, one) == (None,)


def _hit(*values: Any, id_: int) -> SearchHit:  # noqa: ANN401
    node = _node("n")
    node.id = uuid.UUID(int=id_)
    return SearchHit(node=node, sort_values=tuple(values))


@pytest.mark.parametrize(
    ("hit_value", "cursor_value", "direction", "expected"),
    [
        (2, 1, "asc", True),
        (1, 2, "asc", False),
        (1, 2, "desc", True),
        (2, 1, "desc", False),
        (None, 1, "asc", True),
        (None, 1, "desc", True),
        (1, None, "asc", False),
        (1, None, "desc", False),
    ],
)
def test_is_after_orders_nulls_last_in_both_directions(
    hit_value: float | None,
    cursor_value: float | None,
    direction: str,
    expected: bool,
) -> None:
    """Is after orders nulls last in both directions."""
    sort = (SortKey(by="field", type="thing", key="count", dir=direction),)  # type: ignore[arg-type]
    cursor = Cursor(sort_values=(cursor_value,), id=uuid.UUID(int=5))
    assert is_after(_hit(hit_value, id_=9), cursor, sort) is expected


def test_is_after_breaks_ties_by_next_key_then_id() -> None:
    """Is after breaks ties by next key then id."""
    sort = (SortKey(by="name"), SortKey(by="created", dir="desc"))
    cursor = Cursor(sort_values=("a", 5.0), id=uuid.UUID(int=5))
    assert is_after(_hit("a", 4.0, id_=1), cursor, sort)
    assert not is_after(_hit("a", 6.0, id_=9), cursor, sort)
    assert is_after(_hit("a", 5.0, id_=6), cursor, sort)
    assert not is_after(_hit("a", 5.0, id_=5), cursor, sort)
    assert not is_after(
        _hit(None, None, id_=5),
        Cursor(sort_values=(None, None), id=uuid.UUID(int=5)),
        sort,
    )


async def test_multi_key_sort_with_nulls_and_descending_ties(
    repository: NodeRepository,
) -> None:
    """Multi key sort with nulls and descending ties."""
    repo = repository
    for name, count in [("b", 1), ("a", 1), ("c", None), ("d", 2)]:
        await repo.add(_node(name, **({} if count is None else {"count": count})))
    raw = {
        "v": 1,
        "where": None,
        "sort": [
            {"by": "field", "type": "thing", "key": "count", "dir": "desc"},
            {"by": "name"},
        ],
    }
    hits = await repo.search(
        scope=AccessScope.of(OWNER), resolved=_resolve(raw), after=None, limit=10
    )
    assert [h.node.name for h in hits] == ["d", "a", "b", "c"]


async def test_table_column_empty_and_not_empty_are_complements(
    repository: NodeRepository,
) -> None:
    """An empty table or a non-list value is empty, never not_empty."""
    nodes = [
        _node("none", parts=[]),
        _node("oops", parts="oops"),
        _node("full", parts=[{"sku": "x"}]),
    ]
    assert await _run(repository, nodes, _f("parts", "empty", sub_key="sku")) == {
        "none",
        "oops",
    }
    assert await _run(repository, nodes, _f("parts", "not_empty", sub_key="sku")) == {
        "full"
    }


@pytest.mark.parametrize(
    "overlay",
    [
        {},
        {"properties": None},
        {"properties": {"label": "text"}},
        {"properties": {"label": {"x-menagerist": "text"}}},
        {"properties": {"label": {"x-menagerist": {"kind": "number"}}}},
        {"properties": {"label": {"x-menagerist": {"kind": "text", "archived": True}}}},
    ],
    ids=[
        "no-properties",
        "properties-not-an-object",
        "field-not-an-object",
        "metadata-not-an-object",
        "other-kind",
        "archived",
    ],
)
async def test_malformed_or_foreign_overlays_never_match(
    repository: NodeRepository, overlay: dict[str, Any]
) -> None:
    """An overlay not declaring the field live with that kind is out of scope."""
    node = _node("a", label="x")
    node.extra_schema = overlay
    per_item = {"kind": "field", "key": "label", "field_kind": "text"}
    for op, value in [("=", "x"), ("!=", "y"), ("not_empty", None)]:
        cond = per_item | {"op": op} | ({} if value is None else {"value": value})
        assert await _run(repository, [node], cond) == set()


async def test_per_item_condition_reads_the_declared_kind_not_the_type(
    repository: NodeRepository,
) -> None:
    """The overlay's kind rules, whatever kind the item's type gives the key."""
    node = _node("a", count="five")
    node.extra_schema = {
        "properties": {"count": {"x-menagerist": {"kind": "text"}}},
    }
    per_item = {"kind": "field", "key": "count", "field_kind": "text"}
    assert await _run(repository, [node], per_item | {"op": "=", "value": "FIVE"}) == {
        "a"
    }
    assert await _run(repository, [node], _f("count", "=", 5)) == set()

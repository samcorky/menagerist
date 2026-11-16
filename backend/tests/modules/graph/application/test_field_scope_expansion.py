from typing import Any

import pytest

from app.modules.graph.application.field_scope_expansion import expand_field_scopes
from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.query import (
    ConnectionCondition,
    FieldCondition,
    Group,
    InvalidQueryError,
    Query,
    parse_query,
)

_STATUS = {
    "type": "string",
    "enum": ["Owned", "Wanted"],
    "x-menagerist": {"kind": "choice", "origin": {"preset": "p-status", "version": 1}},
}
_ACQUIRED = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "date": {"type": "string", "x-menagerist": {"kind": "partialdate"}},
            "gone": {"type": "string", "x-menagerist": {"archived": True}},
        },
    },
    "x-menagerist": {"kind": "group", "origin": {"preset": "p-acq", "version": 1}},
}
SCHEMAS: dict[str, dict[str, Any]] = {
    "film": {"properties": {"status": _STATUS, "acquired": _ACQUIRED}},
    "game": {"properties": {"status_2": _STATUS, "status": {"type": "number"}}},
    "book": {
        "properties": {
            "status": {"type": "string", "x-menagerist": {"kind": "choice"}},
            "acquired": _ACQUIRED | {"x-menagerist": {"kind": "group"}},
        }
    },
    "toy": {
        "properties": {
            "status": {"x-menagerist": {"kind": "choice", "archived": True}},
            "loose": "not a property",
        }
    },
    "bare": {},
}


def _expand(condition: dict[str, Any]) -> Group | FieldCondition:
    query = parse_query({"v": 1, "where": {"op": "and", "children": [condition]}})
    where = expand_field_scopes(query.where, SCHEMAS)
    assert where is not None
    (child,) = where.children
    assert isinstance(child, Group | FieldCondition)
    return child


def _types(node: object) -> list[tuple[str | None, str, str | None]]:
    assert isinstance(node, Group)
    assert node.op == "or"
    return [
        (c.type, c.key, c.field_kind)
        for c in node.children
        if isinstance(c, FieldCondition)
    ]


def _any(**extra: Any) -> dict[str, Any]:  # noqa: ANN401
    base = {"kind": "field", "field_kind": "choice", "key": "status", "op": "="}
    return base | {"value": "Wanted"} | extra


def test_key_and_kind_reach_every_type_and_the_items_own_fields() -> None:
    """Same key and kind on two types; other kinds and archived fields are skipped."""
    assert _types(_expand(_any())) == [
        ("film", "status", None),
        ("book", "status", None),
        (None, "status", "choice"),
    ]


def test_a_column_reaches_table_fields_only() -> None:
    """Overlays have no columns, so no overlay leaf; archived columns are skipped."""
    found = _expand(
        _any(field_kind="partialdate", key="acquired", sub_key="date", value="2022")
    )
    assert _types(found) == [("film", "acquired", None), ("book", "acquired", None)]
    gone = _expand(_any(field_kind="text", key="acquired", sub_key="gone", value="x"))
    assert isinstance(gone, FieldCondition)
    missing = _expand(_any(field_kind="text", key="status", sub_key="x", value="x"))
    assert isinstance(missing, FieldCondition)


def test_origin_reaches_copies_whatever_their_key() -> None:
    """The copy on games is `status_2`; the book's own status has no origin."""
    found = _expand(
        {"kind": "field", "origin": "p-status", "op": "=", "value": "Wanted"}
    )
    assert _types(found) == [("film", "status", None), ("game", "status_2", None)]


def test_origin_on_a_column() -> None:
    """A saved table field's column is reached on every type copied from it."""
    found = _expand(
        {
            "kind": "field",
            "origin": "p-acq",
            "sub_key": "date",
            "op": ">=",
            "value": "2022",
        }
    )
    assert _types(found) == [("film", "acquired", None)]


def test_nothing_reached_stays_and_resolves_stale_without_a_warning() -> None:
    """A later type may match, so there is no warning; until then nothing matches."""
    query = parse_query(
        {
            "v": 1,
            "where": {
                "op": "and",
                "children": [{"kind": "field", "origin": "p-none", "op": "empty"}],
            },
        }
    )
    where = expand_field_scopes(query.where, SCHEMAS)
    assert where == query.where
    resolution = resolve_fields(Query(where=where), SCHEMAS)
    assert resolution.warnings == []
    assert len(resolution.stale) == 1


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        (_any(field_kind="nope"), "Unknown field kind"),
        (_any(op=">"), "does not fit a choice field"),
        (_any(value=3), "does not fit a choice field"),
        (
            {"kind": "field", "origin": "p-status", "op": "=", "value": 3},
            "does not fit this saved field",
        ),
    ],
)
def test_misfits_are_refused_at_the_condition(
    condition: dict[str, Any], message: str
) -> None:
    """Checked once against the named kind, or against every copy of the saved field."""
    with pytest.raises(InvalidQueryError, match=message) as caught:
        _expand(condition)
    assert caught.value.path == "where.children[0]"


def test_expanded_leaves_resolve_as_ordinary_type_fields() -> None:
    """The rewritten tree passes resolution and records each type's field kind."""
    query = parse_query({"v": 1, "where": {"op": "and", "children": [_any()]}})
    resolution = resolve_fields(
        Query(where=expand_field_scopes(query.where, SCHEMAS)), SCHEMAS
    )
    assert resolution.kinds == {
        ("film", "status", None): "choice",
        ("book", "status", None): "choice",
    }
    assert resolution.stale == frozenset()


def test_nested_groups_and_connection_filters_are_expanded() -> None:
    """Expansion reaches into sub-groups and a connection's far-end filter."""
    raw = {
        "v": 1,
        "where": {
            "op": "and",
            "children": [
                {"op": "not", "children": [_any()]},
                {
                    "kind": "connection",
                    "mode": "exists",
                    "relationship": "part-of",
                    "direction": "out",
                    "where": {"op": "and", "children": [_any()]},
                },
                {"kind": "favourite", "value": True},
            ],
        },
    }
    where = expand_field_scopes(parse_query(raw).where, SCHEMAS)
    assert where is not None
    negated, connection, favourite = where.children
    assert isinstance(negated, Group)
    assert len(_types(negated.children[0])) == 3
    assert isinstance(connection, ConnectionCondition)
    assert connection.where is not None
    assert len(_types(connection.where.children[0])) == 3
    assert favourite == parse_query(raw).where.children[2]  # type: ignore[union-attr]


def test_no_filter_stays_none() -> None:
    """A query with no filter has nothing to expand."""
    assert expand_field_scopes(None, SCHEMAS) is None

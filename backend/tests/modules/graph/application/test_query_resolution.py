from typing import Any

import pytest

from app.modules.graph.application.query_resolution import resolve_fields
from app.modules.graph.domain.query import (
    FieldCondition,
    FieldReference,
    Group,
    InvalidQueryError,
    Query,
    parse_query,
)

SCHEMAS: dict[str, dict[str, Any]] = {
    "film": {
        "type": "object",
        "properties": {
            "rating": {"type": "number", "x-menagerist": {"kind": "rating"}},
            "year": {"type": "string", "x-menagerist": {"kind": "partialdate"}},
            "old": {"type": "string", "x-menagerist": {"archived": True}},
            "genres": {"type": "array", "items": {"type": "string", "enum": ["a"]}},
            "stock": {"type": "number"},
            "reorder_at": {"type": "number"},
            "title_en": {"type": "string"},
            "cast": {
                "type": "array",
                "items": {"type": "object", "properties": {"role": {"type": "string"}}},
                "x-menagerist": {"kind": "group"},
            },
        },
    }
}


def _where(*children: dict[str, Any]) -> Query:
    return parse_query({"v": 1, "where": {"op": "and", "children": list(children)}})


def _f(key: str, op: str, value: Any = None, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    cond = {"kind": "field", "type": "film", "key": key, "op": op, **extra}
    if value is not None:
        cond["value"] = value
    return cond


def test_resolves_known_fields() -> None:
    """Resolves known fields."""
    result = resolve_fields(
        _where(_f("rating", ">=", 4), _f("cast", "~", "x", sub_key="role")), SCHEMAS
    )
    assert result.kinds == {
        ("film", "rating", None): "rating",
        ("film", "cast", "role"): "text",
    }
    assert result.warnings == []


@pytest.mark.parametrize(
    ("condition", "fragment"),
    [
        (_f("old", "=", "x"), "no longer exists"),
        (_f("missing", "=", "x"), "no longer exists"),
        (
            {"kind": "field", "type": "gone", "key": "rating", "op": ">=", "value": 1},
            "no longer exists",
        ),
        (_f("cast", "=", "x", sub_key="gone"), "no longer exists"),
    ],
)
def test_stale_fields_warn_instead_of_failing(
    condition: dict[str, Any], fragment: str
) -> None:
    """Stale fields warn instead of failing."""
    result = resolve_fields(_where(condition), SCHEMAS)
    assert result.kinds == {}
    assert [w.path for w in result.warnings] == ["where.children[0]"]
    assert fragment in result.warnings[0].message


@pytest.mark.parametrize(
    "condition",
    [
        _f("rating", "~", "x"),  # operator not offered for the kind
        _f("rating", ">=", "high"),  # text value for a number
        _f("year", "=", 1984),  # number for a partial date
        _f("year", "=", "19x4"),  # not a partial date
        _f("genres", "has", 3),
        _f("rating", "=", {"ref": "title_en"}),  # reference of a different kind
        _f("year", "=", {"ref": "year"}),  # kind that cannot take references
        _f("rating", "not_in", [1]),  # not_in is not offered for numbers
        _f("genres", "not_in", ["a"]),  # nor for multi-choice
        _f("title_en", "not_in", ["a", 3]),  # every operand must fit the kind
        _f("title_en", "not_in", [{"ref": "title_en"}]),  # text takes no references
    ],
)
def test_wrong_operator_or_value_is_an_error(condition: dict[str, Any]) -> None:
    """Wrong operator or value is an error."""
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(_where(condition), SCHEMAS)


def test_field_reference_to_a_stale_field_warns() -> None:
    """Field reference to a stale field warns."""
    result = resolve_fields(_where(_f("stock", "<=", {"ref": "gone"})), SCHEMAS)
    assert result.kinds == {}
    assert len(result.warnings) == 1


def test_stale_conditions_are_listed_even_when_their_field_is_live() -> None:
    """A stale reference stays stale beside a live condition on the same field."""
    query = _where(
        _f("stock", "<=", {"ref": "gone"}),
        _f("stock", "not_empty"),
        _f("gone", "empty"),
    )
    result = resolve_fields(query, SCHEMAS)
    assert result.kinds == {("film", "stock", None): "number"}
    assert result.stale == {
        FieldCondition(
            type="film", key="stock", op="<=", value=FieldReference(key="gone")
        ),
        FieldCondition(type="film", key="gone", op="empty"),
    }


def test_field_reference_of_the_same_kind_resolves() -> None:
    """Field reference of the same kind resolves."""
    result = resolve_fields(_where(_f("stock", "<=", {"ref": "reorder_at"})), SCHEMAS)
    assert result.kinds == {("film", "stock", None): "number"}


def test_sort_keys_resolve_and_must_be_sortable() -> None:
    """Sort keys resolve and must be sortable."""
    sort_rating = {
        "v": 1,
        "where": None,
        "sort": [{"by": "field", "type": "film", "key": "rating"}],
    }
    assert resolve_fields(parse_query(sort_rating), SCHEMAS).kinds == {
        ("film", "rating", None): "rating"
    }
    sort_genres = {
        "v": 1,
        "where": None,
        "sort": [{"by": "field", "type": "film", "key": "genres"}],
    }
    with pytest.raises(InvalidQueryError, match=r"sort\[0\]"):
        resolve_fields(parse_query(sort_genres), SCHEMAS)


def _date_query(op: str, value: Any) -> Query:  # noqa: ANN401
    cond = {"kind": "date", "on": "created", "op": op, "value": value}
    return _where(cond)


def test_date_condition_value_must_be_a_date() -> None:
    """Date condition value must be a date."""
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(_date_query(">=", "soon"), SCHEMAS)
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(_date_query(">=", 5), SCHEMAS)
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(_date_query("between", ["2024-01-01", "soon"]), SCHEMAS)


def test_date_condition_accepts_iso_and_relative_dates() -> None:
    """Date condition accepts iso and relative dates."""
    assert resolve_fields(_date_query(">=", "2024-01-31"), SCHEMAS).warnings == []
    assert resolve_fields(_date_query("<", {"rel": "-30d"}), SCHEMAS).warnings == []
    result = resolve_fields(
        _date_query("between", ["2024-01-01", {"rel": "1y"}]), SCHEMAS
    )
    assert result.kinds == {}


def test_non_field_conditions_are_ignored() -> None:
    """Non field conditions are ignored."""
    query = _where({"kind": "text", "q": "x"}, {"kind": "favourite", "value": True})
    assert resolve_fields(query, SCHEMAS).warnings == []


def test_unfilterable_field_is_an_error() -> None:
    """Unfilterable field is an error."""
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(_where(_f("cast", "empty")), SCHEMAS)


@pytest.mark.parametrize(
    "condition",
    [
        _f("rating", "empty"),
        _f("rating", "between", [1, 5]),
        _f("year", "=", {"rel": "-1y"}),
        _f("year", ">", "1984-05"),
        _f("genres", "has", "a"),
        _f("title_en", "in", ["a", "b"]),
        _f("title_en", "not_in", ["a", "b"]),
        _f("cast", "not_in", ["lead"], sub_key="role"),
    ],
)
def test_valid_conditions_resolve(condition: dict[str, Any]) -> None:
    """Valid conditions resolve."""
    assert len(resolve_fields(_where(condition), SCHEMAS).kinds) == 1


def test_column_cannot_be_compared_with_a_field() -> None:
    """Column cannot be compared with a field."""
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(
            _where(_f("cast", "=", {"ref": "stock"}, sub_key="role")), SCHEMAS
        )


def test_reference_in_a_list_is_checked_per_operand() -> None:
    """Reference in a list is checked per operand."""
    result = resolve_fields(
        _where(_f("stock", "between", [1, {"ref": "gone"}])), SCHEMAS
    )
    assert result.kinds == {}
    assert len(result.warnings) == 1


def test_sort_on_a_stale_field_warns() -> None:
    """Sort on a stale field warns."""
    query = parse_query(
        {
            "v": 1,
            "where": None,
            "sort": [{"by": "field", "type": "film", "key": "gone"}],
        }
    )
    result = resolve_fields(query, SCHEMAS)
    assert result.kinds == {}
    assert [w.path for w in result.warnings] == ["sort[0]"]


def test_sort_on_name_needs_no_schema() -> None:
    """Sort on name needs no schema."""
    query = parse_query({"v": 1, "where": None, "sort": [{"by": "name"}]})
    assert resolve_fields(query, SCHEMAS) == resolve_fields(
        parse_query({"v": 1, "where": None}), SCHEMAS
    )


def test_money_values_are_checked() -> None:
    """Money values are checked."""
    schemas = {
        "film": {
            "properties": {
                "price": {"type": "object", "x-menagerist": {"kind": "money"}}
            }
        }
    }
    ok = _f("price", ">", {"value": 3, "currency": "GBP"})
    assert len(resolve_fields(_where(ok), schemas).kinds) == 1
    with pytest.raises(InvalidQueryError):
        resolve_fields(_where(_f("price", ">", 3)), schemas)


def test_boolean_and_date_field_values() -> None:
    """Boolean and date field values."""
    schemas = {
        "film": {
            "properties": {
                "seen": {"type": "boolean"},
                "released": {"type": "string", "format": "date"},
            }
        }
    }
    assert (
        len(
            resolve_fields(
                _where(_f("seen", "=", True), _f("released", ">", "2024-02-03")),
                schemas,
            ).kinds
        )
        == 2
    )
    assert (
        len(resolve_fields(_where(_f("released", ">", {"rel": "-1d"})), schemas).kinds)
        == 1
    )
    with pytest.raises(InvalidQueryError):
        resolve_fields(_where(_f("released", ">", "2024-13-45")), schemas)
    with pytest.raises(InvalidQueryError):
        resolve_fields(_where(_f("released", ">", 3)), schemas)
    with pytest.raises(InvalidQueryError):
        resolve_fields(_where(_f("seen", "=", "yes")), schemas)


def test_checklist_and_relative_date_on_number_fail() -> None:
    """Checklist and relative date on number fail."""
    schemas = {
        "film": {
            "properties": {
                "todo": {"type": "array", "x-menagerist": {"kind": "checklist"}}
            }
        }
    }
    assert len(resolve_fields(_where(_f("todo", "incomplete")), schemas).kinds) == 1
    with pytest.raises(InvalidQueryError):
        resolve_fields(_where(_f("rating", ">", {"rel": "-1d"})), SCHEMAS)


def test_condition_built_without_a_value_has_nothing_to_check() -> None:
    """A hand-built condition with no value still resolves."""
    condition = FieldCondition(type="film", key="rating", op="=")
    query = Query(where=Group(op="and", children=(condition,)))
    assert resolve_fields(query, SCHEMAS).kinds == {("film", "rating", None): "rating"}


_DATE_SCHEMAS: dict[str, dict[str, Any]] = {
    "film": {
        "properties": {
            "released": {"type": "string", "format": "date"},
            "year": {"type": "string", "x-menagerist": {"kind": "partialdate"}},
        }
    }
}


@pytest.mark.parametrize(
    "value",
    [
        "20240101",
        "2024-W01-1",
        "2024W011",
        "2024-001",
        "2024-01-01\n",
        "2024-01-01".translate({ord(str(d)): 0x660 + d for d in range(10)}),
        "2024-01-01T00:00",
    ],
)
def test_dates_must_be_extended_iso_calendar_dates(value: str) -> None:
    """Basic, week and ordinal forms would compare wrongly as text: a 400."""
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(_where(_f("released", ">", value)), _DATE_SCHEMAS)
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(_date_query(">", value), _DATE_SCHEMAS)


@pytest.mark.parametrize(
    "value",
    [
        "1984\n",
        "1984".translate({ord(str(d)): 0x660 + d for d in range(10)}),
        "1984-06\n",
        "1984-6",
    ],
)
def test_partial_dates_must_be_plain_ascii(value: str) -> None:
    """A trailing newline or non-ASCII digits are rejected, as in the browser."""
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        resolve_fields(_where(_f("year", "=", value)), _DATE_SCHEMAS)


@pytest.mark.parametrize("value", ["1984", "1984-06", "1984-06-01"])
def test_partial_dates_of_each_precision_are_accepted(value: str) -> None:
    """Year, month and day precision all resolve."""
    result = resolve_fields(_where(_f("year", "=", value)), _DATE_SCHEMAS)
    assert result.kinds == {("film", "year", None): "partialdate"}

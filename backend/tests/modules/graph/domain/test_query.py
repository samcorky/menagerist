from datetime import date
from typing import Any

import pytest

from app.modules.graph.domain.query import (
    MAX_CONDITIONS,
    MAX_DEPTH,
    MAX_LIST_LENGTH,
    MAX_TEXT_LENGTH,
    FieldCondition,
    FieldReference,
    Group,
    InvalidQueryError,
    Money,
    RelativeDate,
    SortKey,
    TagCondition,
    parse_query,
    walk_conditions,
)


def _query(where: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"v": 1, "where": where, **extra}


def _field(**kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
    return {
        "kind": "field",
        "type": "film",
        "key": "rating",
        "op": ">=",
        "value": 4,
        **kwargs,
    }


def test_parses_a_nested_tree() -> None:
    """A nested tree parses with sort keys and ordered condition paths."""
    query = parse_query(
        _query(
            {
                "op": "and",
                "children": [
                    {"kind": "favourite", "value": True},
                    {
                        "op": "or",
                        "children": [
                            _field(),
                            {"kind": "tag", "mode": "any", "tags": ["noir"]},
                        ],
                    },
                ],
            },
            sort=[{"by": "field", "type": "film", "key": "rating", "dir": "desc"}],
        )
    )
    assert isinstance(query.where, Group)
    assert query.sort == (SortKey(by="field", dir="desc", type="film", key="rating"),)
    paths = [path for path, _ in walk_conditions(query.where)]
    assert paths == [
        "where.children[0]",
        "where.children[1].children[0]",
        "where.children[1].children[1]",
    ]


def test_no_where_means_everything() -> None:
    """A missing where clause means no filter."""
    assert parse_query(_query(None)).where is None


def _and(*children: dict[str, Any]) -> dict[str, Any]:
    return {"op": "and", "children": list(children)}


def test_operand_forms_parse() -> None:
    """Relative, reference and money operands parse."""
    cases = [
        ({"rel": "-30d"}, RelativeDate(amount=-30, unit="d")),
        ({"ref": "reorder_at"}, FieldReference(key="reorder_at")),
        ({"value": 3.5, "currency": "GBP"}, Money(value=3.5, currency="GBP")),
    ]
    for raw, expected in cases:
        query = parse_query(_query(_and(_field(op="=", value=raw))))
        assert isinstance(query.where, Group)
        condition = query.where.children[0]
        assert isinstance(condition, FieldCondition)
        assert condition.value == expected


def test_between_and_in_and_has_take_lists() -> None:
    """List operators produce tuples; has accepts a scalar."""
    query = parse_query(
        _query(
            _and(
                _field(op="between", value=[1, 5]),
                _field(key="g", op="has", value="scifi"),
                _field(key="c", op="in", value=["a", "b"]),
            )
        )
    )
    assert isinstance(query.where, Group)
    between, has, in_ = query.where.children
    assert isinstance(between, FieldCondition)
    assert between.value == (1, 5)
    assert isinstance(has, FieldCondition)
    assert has.value == ("scifi",)
    assert isinstance(in_, FieldCondition)
    assert in_.value == ("a", "b")


def test_not_in_takes_a_list_like_in() -> None:
    """`not_in` parses to a tuple of operands, exactly as `in` does."""
    query = parse_query(
        _query(_and(_field(key="c", op="not_in", value=["a", 1, {"ref": "k"}])))
    )
    assert isinstance(query.where, Group)
    (condition,) = query.where.children
    assert isinstance(condition, FieldCondition)
    assert condition.op == "not_in"
    assert condition.value == ("a", 1, FieldReference(key="k"))


@pytest.mark.parametrize("size", [1, MAX_LIST_LENGTH])
def test_not_in_accepts_one_to_fifty_values(size: int) -> None:
    """The list limits of `in` apply to `not_in`."""
    items = ["a"] * (size - 1) + ["x" * MAX_TEXT_LENGTH]
    query = parse_query(_query(_and(_field(op="not_in", value=items))))
    assert isinstance(query.where, Group)
    condition = query.where.children[0]
    assert isinstance(condition, FieldCondition)
    assert condition.value == tuple(items)


@pytest.mark.parametrize(
    "value",
    [
        [],
        "a",
        ["a"] * (MAX_LIST_LENGTH + 1),
        ["a", None],
        [["a"]],
        ["x" * (MAX_TEXT_LENGTH + 1)],
        [float("nan")],
    ],
    ids=["empty", "scalar", "51", "null", "nested", "too long", "nan"],
)
def test_not_in_rejects_what_in_rejects(value: object) -> None:
    """`not_in` needs a list of 1 to 50 valid operands, as `in` does."""
    for op in ("in", "not_in"):
        with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
            parse_query(_query(_and(_field(op=op, value=value))))


def test_not_in_without_a_value_is_rejected() -> None:
    """`not_in` needs a value."""
    condition = {k: v for k, v in _field(op="not_in").items() if k != "value"}
    with pytest.raises(InvalidQueryError, match="'not_in' needs a value"):
        parse_query(_query(_and(condition)))


def test_not_in_is_not_a_date_operator() -> None:
    """Created and updated dates do not take `not_in`."""
    date_condition = {"kind": "date", "on": "created", "op": "not_in", "value": [1]}
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        parse_query(_query(_and(date_condition)))


def test_no_value_operators_reject_a_value() -> None:
    """Operators that take no value reject one, naming the path."""
    with pytest.raises(InvalidQueryError, match=r"where\.children\[0\]"):
        parse_query(_query(_and(_field(op="empty", value=1))))


@pytest.mark.parametrize(
    "bad",
    [
        "not an object",
        {"v": 2, "where": None},
        {"v": 1, "where": {"op": "xor", "children": [_field()]}},
        {"v": 1, "where": {"op": "and", "children": []}},
        {"v": 1, "where": {"op": "not", "children": [_field(), _field()]}},
        {"v": 1, "where": _and({"kind": "nope"})},
        {"v": 1, "where": _and(_field(op="between", value=[1]))},
        {"v": 1, "where": _and(_field(op="~~"))},
        {"v": 1, "where": _and({"kind": "tag", "mode": "some", "tags": ["a"]})},
        {"v": 1, "where": _and(_field(value={"rel": "soon"}))},
        {"v": 1, "where": _and(_field(value=[1, 2]))},
        {"v": 1, "where": _and(_field(value=None))},
        {"v": 1, "where": None, "sort": [{"by": "field"}]},
        {"v": 1, "where": None, "sort": [{"by": "name"}] * 4},
        {"v": 1, "where": None, "sort": "name"},
        {"v": 1, "where": _and(_field(value={"value": True, "currency": "GBP"}))},
        {"v": 1, "where": _and({"kind": "tag", "mode": [], "tags": ["a"]})},
        {"v": 1, "where": _and({"kind": "date", "on": {}, "op": ">", "value": 1})},
        {"v": 1, "where": None, "sort": [{"by": []}]},
        {"v": 1, "where": None, "sort": [{"by": "name", "dir": []}]},
        {"v": 1, "where": {"op": [], "children": [_field()]}},
        {"v": 1, "where": _and({"kind": []})},
        {"v": 1, "where": None, "sort": [{"by": "name", "dir": "up"}]},
        {"v": 1, "where": None, "sort": ["name"]},
        {"v": 1, "where": "everything"},
        {"v": 1, "where": {"op": "and", "children": "x"}},
        {"v": 1, "where": {"op": "and", "children": ["not a condition"]}},
        {"v": 1, "where": _and({"kind": "type", "in": []})},
        {"v": 1, "where": _and({"kind": "favourite", "value": "yes"})},
        {
            "v": 1,
            "where": _and({"kind": "date", "on": "deleted", "op": ">", "value": 1}),
        },
        {
            "v": 1,
            "where": _and({"kind": "date", "on": "created", "op": "in", "value": [1]}),
        },
        {"v": 1, "where": _and(_field(op="empty") | {"value": None})},
        {"v": 1, "where": _and({k: v for k, v in _field().items() if k != "value"})},
        {"v": 1, "where": _and(_field(op="in", value=[]))},
        {"v": 1, "where": _and(_field(op="in", value="a"))},
        {"v": 1, "where": _and(_field(op="between", value="ab"))},
        {"v": 1, "where": _and(_field(value="x" * 201))},
        {"v": 1, "where": _and(_field(value={"value": "n", "currency": "GBP"}))},
        {"v": 1, "where": _and(_field(sub_key=""))},
    ],
)
def test_rejects_malformed_queries(bad: object) -> None:
    """Malformed queries are rejected."""
    with pytest.raises(InvalidQueryError):
        parse_query(bad)


def test_depth_limit() -> None:
    """Nesting beyond the depth limit is rejected."""
    where: dict[str, Any] = _and(_field())
    for _ in range(MAX_DEPTH):
        where = _and(where)
    with pytest.raises(InvalidQueryError, match="nested"):
        parse_query(_query(where))


def test_condition_limit() -> None:
    """More conditions than the limit are rejected."""
    where = _and(*[_field() for _ in range(MAX_CONDITIONS + 1)])
    with pytest.raises(InvalidQueryError, match=str(MAX_CONDITIONS)):
        parse_query(_query(where))


def test_overlong_text_is_rejected() -> None:
    """Over-long text is rejected."""
    with pytest.raises(InvalidQueryError):
        parse_query(_query(_and({"kind": "text", "q": "x" * 201})))


def test_tag_condition_shape() -> None:
    """Tag conditions keep mode and tags."""
    query = parse_query(
        _query(_and({"kind": "tag", "mode": "none", "tags": ["a", "b"]}))
    )
    assert isinstance(query.where, Group)
    assert query.where.children[0] == TagCondition(mode="none", tags=("a", "b"))


@pytest.mark.parametrize(
    ("today", "rel", "expected"),
    [
        (date(2026, 10, 14), RelativeDate(amount=-30, unit="d"), date(2026, 9, 14)),
        (date(2026, 10, 14), RelativeDate(amount=1, unit="w"), date(2026, 10, 21)),
        (date(2026, 3, 31), RelativeDate(amount=-1, unit="m"), date(2026, 2, 28)),
        (date(2024, 3, 31), RelativeDate(amount=-1, unit="m"), date(2024, 2, 29)),
        (date(2024, 2, 29), RelativeDate(amount=-1, unit="y"), date(2023, 2, 28)),
    ],
)
def test_relative_dates_resolve_and_clamp(
    today: date, rel: RelativeDate, expected: date
) -> None:
    """Relative dates resolve and clamp to month ends."""
    assert rel.resolve(today) == expected


def test_walking_no_tree_yields_nothing() -> None:
    """An absent tree has no conditions."""
    assert list(walk_conditions(None)) == []


def test_remaining_condition_kinds_parse() -> None:
    """Text, type, favourite, date, sub-key and plain sort forms parse."""
    query = parse_query(
        _query(
            _and(
                {"kind": "text", "q": "noir"},
                {"kind": "type", "in": ["film"]},
                {"kind": "date", "on": "created", "op": ">=", "value": {"rel": "-1w"}},
                _field(sub_key="price"),
            ),
            sort=[{"by": "name"}, {"by": "created", "dir": "desc"}],
        )
    )
    assert isinstance(query.where, Group)
    kinds = [type(child).__name__ for child in query.where.children]
    assert kinds == [
        "TextCondition",
        "TypeCondition",
        "DateCondition",
        "FieldCondition",
    ]
    field = query.where.children[3]
    assert isinstance(field, FieldCondition)
    assert field.sub_key == "price"
    assert query.sort == (SortKey(by="name"), SortKey(by="created", dir="desc"))


def test_no_value_operator_parses_without_a_value() -> None:
    """An operator such as empty takes no value."""
    field = {"kind": "field", "type": "film", "key": "rating", "op": "empty"}
    query = parse_query(_query(_and(field)))
    assert isinstance(query.where, Group)
    condition = query.where.children[0]
    assert isinstance(condition, FieldCondition)
    assert condition.value is None


# Backend-only: JSON fixtures cannot carry NaN or lone surrogates portably, and
# huge integers would round-trip differently through JavaScript.
_HUGE = 10**400
_SURROGATE = "\ud800"


@pytest.mark.parametrize(
    "operand",
    [
        _HUGE,
        -_HUGE,
        10**309,
        float("nan"),
        float("inf"),
        float("-inf"),
        {"value": _HUGE, "currency": "GBP"},
        {"value": float("nan"), "currency": "GBP"},
        {"value": float("inf"), "currency": "GBP"},
        _SURROGATE,
        f"ok{_SURROGATE}",
        {"ref": _SURROGATE},
        {"value": 1, "currency": _SURROGATE},
    ],
    ids=[
        "huge integer",
        "huge negative integer",
        "integer just past float range",
        "NaN",
        "Infinity",
        "-Infinity",
        "huge money",
        "NaN money",
        "Infinity money",
        "lone surrogate",
        "text with a lone surrogate",
        "reference with a lone surrogate",
        "currency with a lone surrogate",
    ],
)
def test_hostile_operands_are_rejected(operand: object) -> None:
    """Values the database cannot take, or compares differently, are a 400."""
    for op, value in (("=", operand), ("in", [1, operand]), ("between", [operand, 1])):
        with pytest.raises(InvalidQueryError) as caught:
            parse_query(_query(_and(_field(op=op, value=value))))
        assert caught.value.path == "where.children[0]"


def test_largest_finite_numbers_are_accepted() -> None:
    """Numbers up to the float range still parse."""
    query = parse_query(
        _query(
            _and(
                _field(value=10**308),
                _field(value=-1.7e308),
                _field(value={"value": 10**308, "currency": "GBP"}),
            )
        )
    )
    assert query.where is not None
    assert len(query.where.children) == 3


@pytest.mark.parametrize(
    "condition",
    [
        {"kind": "text", "q": _SURROGATE},
        {"kind": "type", "in": [_SURROGATE]},
        {"kind": "tag", "mode": "any", "tags": [_SURROGATE]},
        _field(key=_SURROGATE),
        _field(type=_SURROGATE),
        _field(sub_key=_SURROGATE),
        _field(key="a\x00b"),
        _field(type=None, field_kind="text", key="a\x00b"),
        _field(type=None, field_kind="text", key="k", op="=", value="a\x00b"),
    ],
    ids=[
        "q",
        "type slug",
        "tag",
        "key",
        "type",
        "sub_key",
        "NUL in a key",
        "NUL in a per-item key",
        "NUL in a per-item value",
    ],
)
def test_lone_surrogates_in_names_are_rejected(condition: dict[str, Any]) -> None:
    """Text that cannot be encoded as UTF-8 is a 400, not a database error."""
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(_query(_and(condition)))
    assert caught.value.path == "where.children[0]"


def test_lone_surrogate_in_a_sort_key_is_rejected() -> None:
    """Sort keys are held to the same text rule."""
    sort = [{"by": "field", "type": "film", "key": _SURROGATE}]
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(_query(None, sort=sort))
    assert caught.value.path == "sort[0]"


def _digits(text: str, zero: int) -> str:
    """`text` with its ASCII digits swapped for another script's."""
    return text.translate({ord(str(d)): zero + d for d in range(10)})


@pytest.mark.parametrize(
    "rel",
    ["-30d\n", _digits("-30d", 0x660), _digits("10d", 0xFF10), "-30d ", "--3d"],
)
def test_relative_dates_must_be_plain_ascii(rel: str) -> None:
    """A trailing newline or non-ASCII digits are rejected, as in the browser."""
    with pytest.raises(InvalidQueryError):
        parse_query(_query(_and(_field(value={"rel": rel}))))


@pytest.mark.parametrize("version", [True, 1.5, "1", None])
def test_version_must_be_exactly_one(version: object) -> None:
    """`true` equals 1 in Python but is not version 1."""
    with pytest.raises(InvalidQueryError) as caught:
        parse_query({"v": version, "where": None})
    assert caught.value.path == "v"


def _per_item(**kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
    base = {
        "kind": "field",
        "key": "signed",
        "field_kind": "boolean",
        "op": "=",
        "value": True,
    }
    return base | kwargs


def test_per_item_condition_parses() -> None:
    """A per-item condition names a field kind instead of an item type."""
    query = parse_query(_query(_and(_per_item())))
    ((_, condition),) = list(walk_conditions(query.where))
    assert condition == FieldCondition(
        key="signed", field_kind="boolean", op="=", value=True
    )
    assert condition.type is None


@pytest.mark.parametrize(
    ("condition", "path"),
    [
        (_per_item(type="film"), "where.children[0]"),
        (
            {k: v for k, v in _per_item().items() if k != "field_kind"},
            "where.children[0]",
        ),
        (_per_item(field_kind=3), "where.children[0]"),
        (_per_item(field_kind=""), "where.children[0]"),
        (_per_item(field_kind="x" * 201), "where.children[0]"),
        (_per_item(sub_key="role"), "where.children[0]"),
        (_per_item(value={"ref": "other"}), "where.children[0]"),
        (_per_item(op="in", value=[1, {"ref": "other"}]), "where.children[0]"),
    ],
)
def test_per_item_condition_rejections_carry_a_path(
    condition: dict[str, Any], path: str
) -> None:
    """Hostile per-item conditions are rejected with the condition's path."""
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(_query(_and(condition)))
    assert caught.value.path == path


def test_a_field_condition_naming_neither_says_so() -> None:
    """The message points at both ways of addressing a field."""
    condition = {k: v for k, v in _per_item().items() if k != "field_kind"}
    with pytest.raises(InvalidQueryError, match="field kind"):
        parse_query(_query(_and(condition)))

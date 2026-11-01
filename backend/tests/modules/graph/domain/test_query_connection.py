import uuid
from typing import Any

import pytest

from app.modules.graph.domain.query import (
    MAX_CONDITIONS,
    ConnectionCondition,
    FavouriteCondition,
    Group,
    InvalidQueryError,
    parse_query,
    walk_conditions,
)

_C = "where.children[0]"
_ITEM = uuid.UUID(int=7)
_FAV = {"kind": "favourite", "value": True}
_WHERE = {"op": "and", "children": [_FAV]}


def _query(condition: dict[str, Any]) -> dict[str, Any]:
    return {"v": 1, "where": {"op": "and", "children": [condition]}}


def _parsed(condition: dict[str, Any]) -> ConnectionCondition:
    group = parse_query(_query(condition)).where
    assert group is not None
    found = group.children[0]
    assert isinstance(found, ConnectionCondition)
    return found


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (
            {"kind": "connection", "mode": "exists"},
            ConnectionCondition(
                mode="exists", relationship=None, direction="any", item=None, where=None
            ),
        ),
        (
            {"kind": "connection", "mode": "none", "relationship": "made-by"},
            ConnectionCondition(
                mode="none",
                relationship="made-by",
                direction="any",
                item=None,
                where=None,
            ),
        ),
        (
            {"kind": "connection", "mode": "exists", "direction": "in"},
            ConnectionCondition(
                mode="exists", relationship=None, direction="in", item=None, where=None
            ),
        ),
        (
            {
                "kind": "connection",
                "mode": "to",
                "relationship": "made-by",
                "direction": "out",
                "item": str(_ITEM),
            },
            ConnectionCondition(
                mode="to",
                relationship="made-by",
                direction="out",
                item=_ITEM,
                where=None,
            ),
        ),
        (
            {"kind": "connection", "mode": "to", "item": str(_ITEM)},
            ConnectionCondition(
                mode="to", relationship=None, direction="any", item=_ITEM, where=None
            ),
        ),
    ],
)
def test_valid_forms_parse(condition: dict[str, Any], expected: object) -> None:
    """Each wire form of the connection condition parses to its dataclass."""
    assert _parsed(condition) == expected


def test_a_far_end_filter_parses_as_a_group() -> None:
    """`where` is a normal group over the far item."""
    for mode in ("exists", "none"):
        parsed = _parsed({"kind": "connection", "mode": mode, "where": _WHERE})
        assert parsed.where == Group(
            op="and", children=(FavouriteCondition(value=True),)
        )


@pytest.mark.parametrize(
    "condition",
    [
        {"kind": "connection"},
        {"kind": "connection", "mode": "some"},
        {"kind": "connection", "mode": 1},
        {"kind": "connection", "mode": "exists", "extra": 1},
        {"kind": "connection", "mode": "exists", "relationship": ""},
        {"kind": "connection", "mode": "exists", "relationship": 3},
        {"kind": "connection", "mode": "exists", "direction": "sideways"},
        {"kind": "connection", "mode": "exists", "direction": 1},
        {"kind": "connection", "mode": "exists", "item": str(_ITEM)},
        {"kind": "connection", "mode": "none", "item": str(_ITEM)},
        {"kind": "connection", "mode": "to"},
        {"kind": "connection", "mode": "to", "item": "not-a-uuid"},
        {"kind": "connection", "mode": "to", "item": 5},
        {"kind": "connection", "mode": "to", "item": str(_ITEM), "where": _WHERE},
        {"kind": "connection", "mode": "exists", "where": {"op": "and"}},
        {"kind": "connection", "mode": "exists", "where": {"children": []}},
        {"kind": "connection", "mode": "exists", "where": "x"},
    ],
)
def test_invalid_forms_are_refused_with_their_path(condition: dict[str, Any]) -> None:
    """Bad modes, directions, ids and unknown keys are rejected at the condition."""
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(_query(condition))
    assert caught.value.path.startswith(_C)


def test_a_bad_far_end_filter_names_its_nested_path() -> None:
    """A problem inside `where` is reported under it."""
    bad = {"op": "and", "children": [{"kind": "favourite"}]}
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(_query({"kind": "connection", "mode": "exists", "where": bad}))
    assert caught.value.path == f"{_C}.where.children[0]"


def test_a_far_end_filter_cannot_hold_a_connection() -> None:
    """One level only, however deep the group nesting inside `where`."""
    inner = {"kind": "connection", "mode": "exists"}
    direct = {"op": "and", "children": [inner]}
    nested = {"op": "or", "children": [{"op": "not", "children": [inner]}]}
    for where, path in (
        (direct, f"{_C}.where.children[0]"),
        (nested, f"{_C}.where.children[0].children[0]"),
    ):
        with pytest.raises(InvalidQueryError, match="far item") as caught:
            parse_query(
                _query({"kind": "connection", "mode": "exists", "where": where})
            )
        assert caught.value.path == path


def test_far_end_conditions_count_towards_the_limit() -> None:
    """The connection itself and each far-end condition use up the 50."""
    far = {"op": "and", "children": [_FAV] * (MAX_CONDITIONS - 1)}
    parse_query(_query({"kind": "connection", "mode": "exists", "where": far}))
    over = {"op": "and", "children": [_FAV] * MAX_CONDITIONS}
    with pytest.raises(InvalidQueryError, match="up to 50") as caught:
        parse_query(_query({"kind": "connection", "mode": "exists", "where": over}))
    assert caught.value.path == f"{_C}.where.children[49]"


def test_the_far_end_filter_has_its_own_depth_limit() -> None:
    """Groups inside `where` nest up to the usual depth."""
    group: dict[str, Any] = {"op": "and", "children": [_FAV]}
    for _ in range(3):
        group = {"op": "and", "children": [group]}
    parse_query(_query({"kind": "connection", "mode": "exists", "where": group}))
    group = {"op": "and", "children": [group]}
    with pytest.raises(InvalidQueryError, match="nested"):
        parse_query(_query({"kind": "connection", "mode": "exists", "where": group}))


def test_walk_conditions_enters_the_far_end_filter() -> None:
    """Far-end conditions are walked, with paths under the condition's `where`."""
    parsed = parse_query(
        _query({"kind": "connection", "mode": "exists", "where": _WHERE})
    )
    paths = [path for path, _ in walk_conditions(parsed.where)]
    assert paths == [_C, f"{_C}.where.children[0]"]

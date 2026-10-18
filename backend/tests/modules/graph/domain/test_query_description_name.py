from typing import Any

import pytest

from app.modules.graph.domain.query import (
    MAX_TEXT_LENGTH,
    DescriptionCondition,
    InvalidQueryError,
    NameCondition,
    parse_query,
    walk_conditions,
)

_C = "where.children[0]"


def _where(condition: dict[str, Any]) -> dict[str, Any]:
    return {"v": 1, "where": {"op": "and", "children": [condition]}}


def _parsed(condition: dict[str, Any]) -> object:
    return next(c for _, c in walk_conditions(parse_query(_where(condition)).where))


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (
            {"kind": "description", "op": "~", "value": "x"},
            DescriptionCondition(op="~", value="x"),
        ),
        (
            {"kind": "description", "op": "~", "value": "y" * MAX_TEXT_LENGTH},
            DescriptionCondition(op="~", value="y" * MAX_TEXT_LENGTH),
        ),
        (
            {"kind": "description", "op": "empty"},
            DescriptionCondition(op="empty"),
        ),
        (
            {"kind": "description", "op": "not_empty"},
            DescriptionCondition(op="not_empty"),
        ),
        ({"kind": "name", "op": "~", "value": "a"}, NameCondition(op="~", value="a")),
        ({"kind": "name", "op": "=", "value": "a"}, NameCondition(op="=", value="a")),
    ],
)
def test_valid_forms_parse(condition: dict[str, Any], expected: object) -> None:
    """Each wire form parses to its dataclass."""
    assert _parsed(condition) == expected


@pytest.mark.parametrize(
    "condition",
    [
        {"kind": "description", "op": "~"},
        {"kind": "description", "op": "~", "value": ""},
        {"kind": "description", "op": "~", "value": "y" * (MAX_TEXT_LENGTH + 1)},
        {"kind": "description", "op": "~", "value": "a\x00b"},
        {"kind": "description", "op": "~", "value": "a\ud800b"},
        {"kind": "description", "op": "~", "value": 5},
        {"kind": "description", "op": "empty", "value": "x"},
        {"kind": "description", "op": "not_empty", "value": ""},
        {"kind": "description", "op": "="},
        {"kind": "description", "op": "=", "value": "x"},
        {"kind": "description", "op": "has", "value": "x"},
        {"kind": "description"},
        {"kind": "description", "op": ["~"], "value": "x"},
        {"kind": "name", "op": "~"},
        {"kind": "name", "op": "="},
        {"kind": "name", "op": "=", "value": ""},
        {"kind": "name", "op": "~", "value": "y" * (MAX_TEXT_LENGTH + 1)},
        {"kind": "name", "op": "~", "value": "a\x00"},
        {"kind": "name", "op": "empty"},
        {"kind": "name", "op": "not_empty"},
        {"kind": "name", "op": "!=", "value": "a"},
        {"kind": "name", "value": "a"},
    ],
)
def test_invalid_forms_are_rejected_with_the_path(condition: dict[str, Any]) -> None:
    """Missing, misplaced or malformed operator and value are 400s with a path."""
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(_where(condition))
    assert caught.value.path == _C


@pytest.mark.parametrize(
    "condition",
    [
        {"kind": "description", "op": "~", "value": "x", "extra": 1},
        {"kind": "description", "op": "empty", "q": "x"},
        {"kind": "name", "op": "=", "value": "x", "mode": "any"},
    ],
)
def test_unknown_keys_are_rejected(condition: dict[str, Any]) -> None:
    """Unknown keys on these conditions are refused with the path."""
    with pytest.raises(InvalidQueryError, match="Unknown key") as caught:
        parse_query(_where(condition))
    assert caught.value.path == _C

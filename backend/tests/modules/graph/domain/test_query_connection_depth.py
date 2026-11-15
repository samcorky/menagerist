"""The `depth` key of a connection condition."""

import uuid
from typing import Any

import pytest

from app.modules.graph.domain.query import (
    ConnectionCondition,
    InvalidQueryError,
    parse_query,
)

_C = "where.children[0]"
_ITEM = uuid.UUID(int=7)


def _query(condition: dict[str, Any]) -> dict[str, Any]:
    return {"v": 1, "where": {"op": "and", "children": [condition]}}


def _parsed(condition: dict[str, Any]) -> ConnectionCondition:
    group = parse_query(_query(condition)).where
    assert group is not None
    found = group.children[0]
    assert isinstance(found, ConnectionCondition)
    return found


def test_depth_defaults_to_one() -> None:
    """A connection with no depth is the existing single hop."""
    assert _parsed({"kind": "connection", "mode": "exists"}).depth == 1


@pytest.mark.parametrize("depth", [1, 2, 25])
def test_a_depth_parses(depth: int) -> None:
    """One hop up to the maximum is accepted with a named directional end."""
    found = _parsed(
        {
            "kind": "connection",
            "mode": "to",
            "item": str(_ITEM),
            "relationship": "contains",
            "direction": "out",
            "depth": depth,
        }
    )
    assert found.depth == depth


@pytest.mark.parametrize(
    "extra",
    [
        {"depth": 0},
        {"depth": 26},
        {"depth": "3"},
        {"depth": True},
        {"depth": 2.5},
        {"depth": 2, "direction": "any"},
        {"depth": 2, "relationship": None},
    ],
)
def test_a_bad_depth_is_refused(extra: dict[str, Any]) -> None:
    """Depth is an integer from 1 to 25; several hops need a relationship and out/in."""
    condition = {
        "kind": "connection",
        "mode": "exists",
        "relationship": "contains",
        "direction": "out",
        **extra,
    }
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(_query(condition))
    assert caught.value.path == _C


def test_several_hops_without_a_direction_are_refused() -> None:
    """Leaving the direction out means 'any', which several hops do not allow."""
    condition = {
        "kind": "connection",
        "mode": "exists",
        "relationship": "contains",
        "depth": 3,
    }
    with pytest.raises(InvalidQueryError):
        parse_query(_query(condition))

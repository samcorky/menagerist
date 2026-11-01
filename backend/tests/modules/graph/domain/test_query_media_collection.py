import uuid
from typing import Any

import pytest

from app.modules.graph.domain.query import (
    CollectionCondition,
    InvalidQueryError,
    ManualTarget,
    MediaCondition,
    SmartTarget,
    parse_query,
    walk_conditions,
)

_C = "where.children[0]"
_ID = uuid.UUID(int=7)
_OTHER = uuid.UUID(int=8)


def _where(condition: dict[str, Any]) -> dict[str, Any]:
    return {"v": 1, "where": {"op": "and", "children": [condition]}}


def _parsed(condition: dict[str, Any]) -> object:
    return next(c for _, c in walk_conditions(parse_query(_where(condition)).where))


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ({"kind": "media", "mode": "has"}, MediaCondition(mode="has")),
        ({"kind": "media", "mode": "none"}, MediaCondition(mode="none")),
        (
            {"kind": "media", "mode": "has", "type": "image"},
            MediaCondition(mode="has", type="image"),
        ),
        (
            {"kind": "media", "mode": "none", "type": "document"},
            MediaCondition(mode="none", type="document"),
        ),
        (
            {"kind": "collection", "mode": "any", "in": [str(_ID)]},
            CollectionCondition(mode="any", ids=(_ID,)),
        ),
        (
            {"kind": "collection", "mode": "none", "in": [str(_ID), str(_OTHER)]},
            CollectionCondition(mode="none", ids=(_ID, _OTHER)),
        ),
    ],
)
def test_valid_forms_parse(condition: dict[str, Any], expected: object) -> None:
    """Each wire form parses to its dataclass."""
    assert _parsed(condition) == expected


@pytest.mark.parametrize(
    "condition",
    [
        {"kind": "media"},
        {"kind": "media", "mode": "some"},
        {"kind": "media", "mode": 1},
        {"kind": "media", "mode": "has", "type": "video"},
        {"kind": "media", "mode": "has", "type": 3},
        {"kind": "media", "mode": "has", "extra": 1},
        {"kind": "collection", "mode": "any"},
        {"kind": "collection", "mode": "all", "in": [str(_ID)]},
        {"kind": "collection", "mode": "any", "in": []},
        {"kind": "collection", "mode": "any", "in": str(_ID)},
        {"kind": "collection", "mode": "any", "in": ["not-a-uuid"]},
        {"kind": "collection", "mode": "any", "in": [5]},
        {
            "kind": "collection",
            "mode": "any",
            "in": [str(uuid.UUID(int=n)) for n in range(51)],
        },
        {"kind": "collection", "mode": "any", "in": [str(_ID)], "extra": 1},
    ],
)
def test_invalid_forms_are_refused_with_their_path(condition: dict[str, Any]) -> None:
    """Bad modes, types, ids and unknown keys are rejected at the condition."""
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(_where(condition))
    assert caught.value.path == _C


def test_fifty_collections_are_allowed() -> None:
    """The list limit is inclusive."""
    ids = [str(uuid.UUID(int=n)) for n in range(50)]
    parsed = _parsed({"kind": "collection", "mode": "any", "in": ids})
    assert isinstance(parsed, CollectionCondition)
    assert len(parsed.ids) == 50


def test_walk_conditions_enters_inlined_smart_collections() -> None:
    """Prepared targets are walked, with paths under the condition's `in`."""
    inner = parse_query(
        {
            "v": 1,
            "where": {"op": "and", "children": [{"kind": "favourite", "value": True}]},
        }
    ).where
    condition = CollectionCondition(
        mode="any",
        ids=(_ID, _OTHER),
        targets=(ManualTarget(id=_ID), SmartTarget(id=_OTHER, where=inner)),
    )
    query = parse_query(_where({"kind": "favourite", "value": False}))
    group = query.where
    assert group is not None
    paths = [
        path
        for path, _ in walk_conditions(type(group)(op="and", children=(condition,)))
    ]
    assert paths == [_C, f"{_C}.in[1].children[0]"]

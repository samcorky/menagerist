"""The shared query-shapes fixture, held against the server's parser.

The frontend decoder is tested against the same file, so a link that decodes
in the browser is also accepted by the server. Bulk cases (long strings, long
lists, many conditions) are generated here rather than stored in the fixture;
`frontend/tests/query-shapes-contract.test.ts` generates the same ones.
"""

import json
from typing import Any

import pytest

from app.modules.graph.domain.query import InvalidQueryError, parse_query
from app.platform.shared_data import shared_data_path

_CONTRACT = json.loads(
    shared_data_path("contracts/query-shapes.json").read_text("utf-8")
)
_C = "where.children[0]"
_FAV = {"kind": "favourite", "value": True}


def _where(*children: object) -> dict[str, Any]:
    return {"v": 1, "where": {"op": "and", "children": list(children)}}


def _field(op: str, **extra: object) -> dict[str, Any]:
    return {"kind": "field", "type": "film", "key": "year", "op": op, **extra}


def _bulk() -> list[tuple[str, dict[str, Any], str | None]]:
    """Generated cases as (name, query, expected error path or None)."""
    cases: list[tuple[str, dict[str, Any], str | None]] = []

    def add(name: str, query: dict[str, Any], path: str | None) -> None:
        cases.append((name, query, path))

    for size, path in ((200, None), (201, _C)):
        text = "a" * size
        add(f"text of {size}", _where({"kind": "text", "q": text}), path)
        add(f"type slug of {size}", _where({"kind": "type", "in": [text]}), path)
        add(
            f"tag of {size}",
            _where({"kind": "tag", "mode": "any", "tags": [text]}),
            path,
        )
        add(f"field type of {size}", _where(_field("=", type=text, value=1)), path)
        add(f"field key of {size}", _where(_field("=", key=text, value=1)), path)
        add(f"sub_key of {size}", _where(_field("=", sub_key=text, value=1)), path)
        add(f"string operand of {size}", _where(_field("=", value=text)), path)
        add(f"reference of {size}", _where(_field("=", value={"ref": text})), path)
        money = {"value": 1, "currency": text}
        add(f"currency of {size}", _where(_field("=", value=money)), path)
        add(
            f"sort type of {size}",
            {
                "v": 1,
                "where": None,
                "sort": [{"by": "field", "type": text, "key": "k"}],
            },
            None if path is None else "sort[0]",
        )
        add(
            f"sort key of {size}",
            {
                "v": 1,
                "where": None,
                "sort": [{"by": "field", "type": "t", "key": text}],
            },
            None if path is None else "sort[0]",
        )
        add(f"in item of {size}", _where(_field("in", value=["a", text])), path)
        add(
            f"between item of {size}",
            _where(_field("between", value=["a", text])),
            path,
        )
        astral = "\U0001f3ac" * size
        add(
            f"tag of {size} astral characters",
            _where({"kind": "tag", "mode": "any", "tags": [astral]}),
            path,
        )
        add(
            f"field key of {size} astral characters",
            _where(_field("=", key=astral, value=1)),
            path,
        )
        add(
            f"string operand of {size} astral characters",
            _where(_field("=", value=astral)),
            path,
        )
    for size, path in ((50, None), (51, _C)):
        items = ["a"] * size
        add(f"type list of {size}", _where({"kind": "type", "in": items}), path)
        add(
            f"tag list of {size}",
            _where({"kind": "tag", "mode": "any", "tags": items}),
            path,
        )
        add(f"in list of {size}", _where(_field("in", value=items)), path)
        add(f"has list of {size}", _where(_field("has", value=items)), path)
    # Length counts characters, not UTF-16 units.
    add(
        "text of 200 astral characters",
        _where({"kind": "text", "q": "\U0001f3ac" * 200}),
        None,
    )
    add(
        "text of 201 astral characters",
        _where({"kind": "text", "q": "\U0001f3ac" * 201}),
        _C,
    )
    for count, path in ((50, None), (51, "where.children[50]")):
        add(f"{count} conditions", _where(*[_FAV] * count), path)
    add(
        "50 conditions across groups",
        {
            "v": 1,
            "where": {
                "op": "and",
                "children": [
                    {"op": "or", "children": [_FAV] * 30},
                    {"op": "or", "children": [_FAV] * 20},
                ],
            },
        },
        None,
    )
    add(
        "conditions counted across groups",
        {
            "v": 1,
            "where": {
                "op": "and",
                "children": [
                    {"op": "or", "children": [_FAV] * 30},
                    {"op": "or", "children": [_FAV] * 21},
                ],
            },
        },
        "where.children[1].children[20]",
    )
    return cases


def test_fixture_is_not_empty() -> None:
    """Guard against the fixture silently losing its cases."""
    assert len(_CONTRACT["valid"]) > 50
    assert len(_CONTRACT["invalid"]) > 100


def test_fixture_names_are_unique() -> None:
    """Names identify failing cases, so they must not repeat."""
    for section in ("valid", "invalid"):
        names = [case["name"] for case in _CONTRACT[section]]
        assert len(names) == len(set(names)), section


@pytest.mark.parametrize(
    "query",
    [case["query"] for case in _CONTRACT["valid"]],
    ids=[case["name"] for case in _CONTRACT["valid"]],
)
def test_valid_shape_parses(query: object) -> None:
    """Every valid fixture query parses."""
    parse_query(query)


@pytest.mark.parametrize(
    ("query", "path"),
    [(case["query"], case["path"]) for case in _CONTRACT["invalid"]],
    ids=[case["name"] for case in _CONTRACT["invalid"]],
)
def test_invalid_shape_is_rejected_at_its_path(query: object, path: str) -> None:
    """Every invalid fixture query is rejected, naming the first problem."""
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(query)
    assert caught.value.path == path


@pytest.mark.parametrize(
    ("query", "path"),
    [(query, path) for _, query, path in _bulk()],
    ids=[name for name, _, _ in _bulk()],
)
def test_generated_boundary_cases(query: object, path: str | None) -> None:
    """Limits hold on both sides: the largest allowed value parses, one more fails."""
    if path is None:
        parse_query(query)
        return
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(query)
    assert caught.value.path == path


@pytest.mark.parametrize(
    ("query", "path"),
    [
        ({"v": 1, "extra": 1}, ""),
        (
            {"v": 1, "where": {"op": "and", "extra": 2, "children": [_FAV]}},
            "where",
        ),
        (_where({**_FAV, "junk": 3}), _C),
        ({"v": 1, "sort": [{"by": "name", "junk": 4}]}, "sort[0]"),
        ({"v": 1, "sort": [{"by": "name", "type": 5, "key": None}]}, "sort[0]"),
    ],
    ids=[
        "query key",
        "group key",
        "condition key",
        "sort key",
        "type and key on a sort that is not by field",
    ],
)
def test_unknown_keys_are_rejected_by_the_server_only(query: object, path: str) -> None:
    """The server stores what it validates, so it refuses keys the grammar lacks.

    The browser decoder rebuilds queries from the known keys and drops the rest,
    so these cases stay out of the shared fixture, which the decoder must reject.
    """
    with pytest.raises(InvalidQueryError) as caught:
        parse_query(query)
    assert caught.value.path == path

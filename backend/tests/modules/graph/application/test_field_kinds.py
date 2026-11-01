import json
from typing import Any

import pytest

from app.modules.graph.application.field_kinds import (
    KIND_OPERATORS,
    NO_VALUE_OPERATORS,
    REF_KINDS,
    kind_of,
)
from app.modules.graph.application.query_resolution import SORTABLE_KINDS
from app.modules.graph.domain import query
from app.platform.shared_data import shared_data_path


def test_operator_table_matches_the_shared_contract() -> None:
    """Backend and frontend read one operator table per field kind."""
    contract = json.loads(
        shared_data_path("contracts/query-operators.json").read_text("utf-8")
    )
    assert {kind: set(ops) for kind, ops in contract.items()} == {
        kind: set(ops) for kind, ops in KIND_OPERATORS.items()
    }


def test_parser_knows_every_operator_a_kind_offers() -> None:
    """An operator offered for a kind is one the parser accepts."""
    offered = set().union(*KIND_OPERATORS.values())
    assert offered <= query._OPERATORS


def test_kind_sets_match_the_shared_contract() -> None:
    """Reference, sortable and no-value sets are the same on both sides."""
    contract = json.loads(
        shared_data_path("contracts/query-kinds.json").read_text("utf-8")
    )
    assert set(contract["ref_kinds"]) == REF_KINDS
    assert set(contract["sortable_kinds"]) == SORTABLE_KINDS
    assert set(contract["no_value_operators"]) == NO_VALUE_OPERATORS
    assert NO_VALUE_OPERATORS == query._NO_VALUE


@pytest.mark.parametrize(
    ("prop", "expected"),
    [
        ({"type": "number", "x-menagerist": {"kind": "duration"}}, "duration"),
        ({"type": "string", "x-menagerist": {"kind": "partialdate"}}, "partialdate"),
        ({"type": "number"}, "number"),
        ({"type": "integer"}, "number"),
        ({"type": "boolean"}, "boolean"),
        ({"type": "string"}, "text"),
        ({"type": "string", "enum": ["a"]}, "choice"),
        ({"type": "string", "format": "date"}, "date"),
        ({"type": "array", "items": {"type": "string", "enum": ["a"]}}, "multichoice"),
        ({"type": "array", "items": {"type": "object"}}, None),
        ({"type": "object", "x-menagerist": {"kind": "opaque"}}, None),
        ({"type": "object"}, None),
        ({"type": "string", "x-menagerist": {"kind": "no-such-kind"}}, "text"),
    ],
)
def test_kind_of(prop: dict[str, Any], expected: str | None) -> None:
    """A property resolves to its filterable kind, or None."""
    assert kind_of(prop) == expected

import json
from typing import Any

import pytest

from app.modules.graph.application.field_kinds import KIND_OPERATORS, kind_of
from app.platform.shared_data import shared_data_path


def test_operator_table_matches_the_shared_contract() -> None:
    """Backend and frontend read one operator table per field kind."""
    contract = json.loads(
        shared_data_path("contracts/query-operators.json").read_text("utf-8")
    )
    assert {kind: set(ops) for kind, ops in contract.items()} == {
        kind: set(ops) for kind, ops in KIND_OPERATORS.items()
    }


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
        ({"type": "string", "x-menagerist": {"kind": "no-such-kind"}}, "text"),
    ],
)
def test_kind_of(prop: dict[str, Any], expected: str | None) -> None:
    """A property resolves to its filterable kind, or None."""
    assert kind_of(prop) == expected

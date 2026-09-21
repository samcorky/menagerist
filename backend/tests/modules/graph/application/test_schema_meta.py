from pathlib import Path
from typing import Any

import pytest

from app.modules.graph.application.schema_meta import (
    archived_keys,
    check_meta_shape,
    required_keys,
    validation_schema,
)
from app.modules.graph.domain.errors import InvalidSchemaError

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["year"],
    "properties": {
        "year": {"type": "number"},
        "old": {"type": "string", "x-menagerist": {"kind": "text", "archived": True}},
        "live": {"type": "string", "x-menagerist": {"archived": False}},
    },
    "x-menagerist": {"version": 1, "required": ["year", 3]},
}


def test_required_keys_reads_the_namespace_and_ignores_non_strings() -> None:
    """Required keys come from the namespace; non-strings are ignored."""
    assert required_keys(_SCHEMA) == ["year"]


@pytest.mark.parametrize(
    "schema",
    [{}, {"x-menagerist": []}, {"x-menagerist": {"required": "year"}}],
)
def test_required_keys_is_empty_when_absent_or_malformed(
    schema: dict[str, Any],
) -> None:
    """Absent or malformed `required` yields no keys."""
    assert required_keys(schema) == []


def test_archived_keys_lists_only_archived_properties() -> None:
    """Only properties flagged archived are returned."""
    assert archived_keys(_SCHEMA) == {"old"}


def test_archived_keys_is_empty_without_properties() -> None:
    """A schema without properties has no archived keys."""
    assert archived_keys({"type": "object"}) == set()


def test_validation_schema_drops_root_required_and_archived_properties() -> None:
    """Root required and archived properties are dropped from a copy."""
    result = validation_schema(_SCHEMA)

    assert "required" not in result
    assert set(result["properties"]) == {"year", "live"}
    assert "required" in _SCHEMA
    assert "old" in _SCHEMA["properties"]


def test_validation_schema_keeps_properties_when_nothing_is_archived() -> None:
    """Nothing is dropped when no property is archived."""
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}

    assert validation_schema(schema) == schema


def test_validation_is_identical_without_the_namespace() -> None:
    """Namespace members never change the validation schema."""
    schema = {
        "type": "object",
        "properties": {"a": {"type": "number", "x-menagerist": {"kind": "number"}}},
        "x-menagerist": {"version": 1, "layout": [{"key": "a"}]},
    }

    assert validation_schema(schema) == schema


def test_check_meta_shape_accepts_valid_and_unknown_members() -> None:
    """Valid members and unknown members pass the shape check."""
    check_meta_shape(
        {
            "properties": {
                "a": {"x-menagerist": {"kind": "text", "future": {"x": 1}}},
                "g": {
                    "type": "array",
                    "items": {
                        "properties": {"s": {"x-menagerist": {"kind": "date"}}},
                    },
                },
                "plain": {"type": "string"},
            },
            "x-menagerist": {"version": 1, "layout": [], "required": ["a"], "z": 0},
        }
    )
    check_meta_shape({"type": "object"})
    check_meta_shape({"properties": {"a": {"items": {"type": "string"}}}})
    check_meta_shape({"properties": {"a": "not-a-dict"}})


@pytest.mark.parametrize(
    "schema",
    [
        {"x-menagerist": "no"},
        {"x-menagerist": {"version": "1"}},
        {"x-menagerist": {"version": True}},
        {"x-menagerist": {"layout": {}}},
        {"x-menagerist": {"required": "a"}},
        {"x-menagerist": {"required": [1]}},
        {"properties": {"a": {"x-menagerist": "no"}}},
        {"properties": {"a": {"x-menagerist": {"kind": 1}}}},
        {"properties": {"a": {"x-menagerist": {"archived": "yes"}}}},
        {"properties": {"a": {"x-menagerist": {"config": []}}}},
        {
            "properties": {
                "g": {"items": {"properties": {"s": {"x-menagerist": {"kind": 1}}}}}
            }
        },
    ],
)
def test_check_meta_shape_rejects_wrongly_typed_members(schema: dict[str, Any]) -> None:
    """Wrongly typed known members are rejected."""
    with pytest.raises(InvalidSchemaError):
        check_meta_shape(schema)


def test_archived_keys_ignores_non_object_properties() -> None:
    """A property that is not an object cannot be archived."""
    assert archived_keys({"properties": {"a": "oops"}}) == set()


def test_only_schema_meta_reads_the_namespace() -> None:
    """No other backend source file refers to the `x-menagerist` keyword."""
    src = Path(__file__).parents[5] / "src"
    offenders = [
        path.name
        for path in src.rglob("*.py")
        if path.name != "schema_meta.py" and "x-menagerist" in path.read_text()
    ]

    assert offenders == []

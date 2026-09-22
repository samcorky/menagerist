from pathlib import Path
from typing import Any

import pytest

from app.modules.graph.application.schema_meta import (
    archived_keys,
    check_meta_shape,
    check_schema_definition,
    merge_attribute_schemas,
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
    check_meta_shape({"properties": {"g": {"x-menagerist": {"columns": ["a", "b"]}}}})
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
        {"properties": {"a": {"x-menagerist": {"columns": "not-a-list"}}}},
        {"properties": {"a": {"x-menagerist": {"columns": [1, 2]}}}},
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


def _with_highlights(highlights: object) -> dict[str, Any]:
    return {
        "properties": {
            "a": {"type": "string"},
            "b": {"type": "number"},
            "c": {"type": "string"},
            "d": {"type": "string"},
            "old": {"type": "string", "x-menagerist": {"archived": True}},
        },
        "x-menagerist": {"highlights": highlights},
    }


def test_check_meta_shape_accepts_valid_highlights() -> None:
    """Up to three unique, live fields pass; other lists are left alone."""
    check_meta_shape(_with_highlights({"card": [{"key": "a"}, {"key": "b"}]}))
    check_meta_shape(_with_highlights({"card": []}))
    check_meta_shape(_with_highlights({}))
    check_meta_shape(_with_highlights({"other": "anything"}))
    check_meta_shape(
        _with_highlights({"card": [{"key": "a"}, {"key": "b"}, {"key": "c"}]})
    )


@pytest.mark.parametrize(
    "highlights",
    [
        "no",
        {"card": "a"},
        {"card": [{"key": "a"}, {"key": "b"}, {"key": "c"}, {"key": "d"}]},
        {"card": ["a"]},
        {"card": [{"key": 1}]},
        {"card": [{}]},
        {"card": [{"key": "a"}, {"key": "a"}]},
        {"card": [{"key": "missing"}]},
        {"card": [{"key": "old"}]},
    ],
)
def test_check_meta_shape_rejects_bad_highlights(highlights: object) -> None:
    """Non-lists, too many, duplicates, unknown and archived keys are rejected."""
    with pytest.raises(InvalidSchemaError):
        check_meta_shape(_with_highlights(highlights))


def test_check_meta_shape_rejects_highlights_without_properties() -> None:
    """A highlight cannot refer to a field when the schema has no properties."""
    with pytest.raises(InvalidSchemaError):
        check_meta_shape({"x-menagerist": {"highlights": {"card": [{"key": "a"}]}}})


def test_check_meta_shape_limits_connection_highlights_to_two() -> None:
    """The connection list allows two fields and follows the same rules."""
    check_meta_shape(_with_highlights({"connection": [{"key": "a"}, {"key": "b"}]}))
    for bad in (
        {"connection": [{"key": "a"}, {"key": "b"}, {"key": "c"}]},
        {"connection": [{"key": "old"}]},
        {"connection": [{"key": "a"}, {"key": "a"}]},
        {"connection": "a"},
    ):
        with pytest.raises(InvalidSchemaError):
            check_meta_shape(_with_highlights(bad))


def test_check_schema_definition_accepts_a_well_shaped_schema() -> None:
    """A valid JSON Schema with a valid `x-menagerist` passes both checks."""
    check_schema_definition({"type": "object", "properties": {"a": {"type": "string"}}})


def test_check_schema_definition_rejects_invalid_json_schema() -> None:
    """A schema jsonschema itself rejects raises InvalidSchemaError."""
    with pytest.raises(InvalidSchemaError):
        check_schema_definition({"type": "not-a-type"})


def test_check_schema_definition_rejects_bad_meta_shape() -> None:
    """A structurally valid schema with a malformed `x-menagerist` still fails."""
    with pytest.raises(InvalidSchemaError):
        check_schema_definition({"type": "object", "x-menagerist": "nope"})


def test_merge_attribute_schemas_returns_none_when_both_are_absent() -> None:
    """Nothing to merge yields None."""
    assert merge_attribute_schemas(None, None) is None


def test_merge_attribute_schemas_returns_the_other_when_one_is_absent() -> None:
    """A single schema passes through unchanged."""
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    assert merge_attribute_schemas(schema, None) == {
        "type": "object",
        "properties": {"a": {"type": "string"}},
    }
    assert merge_attribute_schemas(None, schema) == {
        "type": "object",
        "properties": {"a": {"type": "string"}},
    }


def test_merge_attribute_schemas_combines_properties_from_both() -> None:
    """Properties from the type and the overlay coexist in the merge."""
    type_schema = {"type": "object", "properties": {"year": {"type": "number"}}}
    extra = {"type": "object", "properties": {"signed": {"type": "boolean"}}}

    merged = merge_attribute_schemas(type_schema, extra)

    assert merged is not None
    assert set(merged["properties"]) == {"year", "signed"}


def test_merge_attribute_schemas_raises_on_a_shared_key() -> None:
    """A per-item field cannot redefine a key the item type already has."""
    type_schema = {"type": "object", "properties": {"year": {"type": "number"}}}
    extra = {"type": "object", "properties": {"year": {"type": "string"}}}

    with pytest.raises(InvalidSchemaError, match="year"):
        merge_attribute_schemas(type_schema, extra)


def test_merge_attribute_schemas_rejects_archived_key_reused_in_overlay() -> None:
    """An archived type field's key stays reserved, even for the overlay."""
    type_schema = {
        "type": "object",
        "properties": {"year": {"type": "number", "x-menagerist": {"archived": True}}},
    }
    extra = {"type": "object", "properties": {"year": {"type": "string"}}}

    with pytest.raises(InvalidSchemaError):
        merge_attribute_schemas(type_schema, extra)


def test_merge_attribute_schemas_concatenates_required_and_layout() -> None:
    """Type fields come first in required and layout, then overlay fields."""
    type_schema = {
        "type": "object",
        "properties": {"year": {"type": "number"}},
        "x-menagerist": {"required": ["year"], "layout": [{"key": "year"}]},
    }
    extra = {
        "type": "object",
        "properties": {"signed": {"type": "boolean"}},
        "x-menagerist": {"required": ["signed"], "layout": [{"key": "signed"}]},
    }

    merged = merge_attribute_schemas(type_schema, extra)

    assert merged is not None
    assert merged["x-menagerist"]["required"] == ["year", "signed"]
    assert merged["x-menagerist"]["layout"] == [{"key": "year"}, {"key": "signed"}]


def test_merge_attribute_schemas_result_validates_identically_to_hand_written() -> None:
    """The merged schema behaves like validate_attributes expects: strippable."""
    merged = merge_attribute_schemas(
        {"type": "object", "properties": {"year": {"type": "number"}}},
        {
            "type": "object",
            "properties": {
                "old": {"type": "string", "x-menagerist": {"archived": True}}
            },
        },
    )
    assert merged is not None
    assert archived_keys(merged) == {"old"}

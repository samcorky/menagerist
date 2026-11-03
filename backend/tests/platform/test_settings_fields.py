"""The field helpers shared by discovery and the generated reference."""

from app.platform.config._fields import inline_schema


def test_inline_schema_replaces_a_top_level_ref_and_drops_the_definitions() -> None:
    """A named type is described in place, keeping the field's own keywords."""
    schema = {
        "$ref": "#/$defs/Mode",
        "description": "Which mode.",
        "$defs": {"Mode": {"enum": ["a", "b"], "type": "string"}},
    }

    assert inline_schema(schema) == {
        "enum": ["a", "b"],
        "type": "string",
        "description": "Which mode.",
    }

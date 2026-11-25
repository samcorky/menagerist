"""How a subtype's fields and settings combine with its parent's (#767)."""

import copy
from typing import Any

from app.modules.graph.application.schema_meta import effective_schema


def _schema(
    *keys: str,
    required: list[str] | None = None,
    layout: list[Any] | None = None,
    highlights: dict[str, list[dict[str, str]]] | None = None,
    archived: tuple[str, ...] = (),
    version: int | None = None,
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for key in keys:
        prop: dict[str, Any] = {"type": "string", "title": key.title()}
        if key in archived:
            prop["x-menagerist"] = {"archived": True}
        properties[key] = prop
    meta: dict[str, Any] = {}
    if required is not None:
        meta["required"] = required
    if layout is not None:
        meta["layout"] = layout
    if highlights is not None:
        meta["highlights"] = highlights
    if version is not None:
        meta["version"] = version
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if meta:
        schema["x-menagerist"] = meta
    return schema


def test_a_type_with_no_parent_keeps_its_own_schema() -> None:
    """Nothing to combine: the schema is returned as it is."""
    own = _schema("width")

    assert effective_schema(None, own) is own
    assert effective_schema(None, None) is None


def test_a_subtype_with_no_fields_of_its_own_gets_its_parents() -> None:
    """The parent's fields are all it has, and the parent's schema is not shared."""
    parent = _schema("condition")

    result = effective_schema(parent, None)

    assert result == parent
    assert result is not parent


def test_a_parents_fields_come_first() -> None:
    """The order is the parent's fields, then the subtype's own."""
    result = effective_schema(_schema("condition", "value"), _schema("width"))

    assert result is not None
    assert list(result["properties"]) == ["condition", "value", "width"]


def test_required_fields_are_the_union() -> None:
    """A required parent field is required of every subtype, without repeats."""
    parent = _schema("condition", "value", required=["condition"])
    own = _schema("width", required=["width", "condition"])

    result = effective_schema(parent, own)

    assert result is not None
    assert result["x-menagerist"]["required"] == ["condition", "width"]


def test_the_json_schema_required_list_is_the_union_too() -> None:
    """The plain `required` keyword is combined the same way, parent first."""
    parent = _schema("condition", "value")
    parent["required"] = ["condition"]
    own = _schema("width")
    own["required"] = ["width", "condition"]

    result = effective_schema(parent, own)

    assert result is not None
    assert result["required"] == ["condition", "width"]


def test_the_layout_is_the_parents_sections_then_the_subtypes() -> None:
    """Parent sections first; a field in neither falls to the default section."""
    parent = _schema("condition", layout=[{"title": "Provenance", "fields": []}])
    own = _schema("width", layout=[{"title": "Size", "fields": ["width"]}])

    result = effective_schema(parent, own)

    assert result is not None
    assert [s["title"] for s in result["x-menagerist"]["layout"]] == [
        "Provenance",
        "Size",
    ]


def test_a_parents_archived_field_stays_archived() -> None:
    """Archived is a flag on the field, so it comes along with it."""
    parent = _schema("condition", "old", archived=("old",))

    result = effective_schema(parent, _schema("width"))

    assert result is not None
    assert result["properties"]["old"]["x-menagerist"] == {"archived": True}
    assert "x-menagerist" not in result["properties"]["condition"]


def test_highlights_are_inherited_when_the_subtype_has_none() -> None:
    """No list of its own means the parent's list."""
    parent = _schema(
        "condition",
        highlights={
            "card": [{"key": "condition"}],
            "connection": [{"key": "condition"}],
        },
    )

    result = effective_schema(parent, _schema("width"))

    assert result is not None
    assert result["x-menagerist"]["highlights"] == {
        "card": [{"key": "condition"}],
        "connection": [{"key": "condition"}],
    }


def test_a_subtypes_own_highlights_replace_the_parents_per_list() -> None:
    """Each list is inherited or replaced on its own, and may name either's fields."""
    parent = _schema(
        "condition",
        highlights={
            "card": [{"key": "condition"}],
            "connection": [{"key": "condition"}],
        },
    )
    own = _schema(
        "width", highlights={"card": [{"key": "width"}, {"key": "condition"}]}
    )

    result = effective_schema(parent, own)

    assert result is not None
    assert result["x-menagerist"]["highlights"] == {
        "card": [{"key": "width"}, {"key": "condition"}],
        "connection": [{"key": "condition"}],
    }


def test_an_empty_list_of_its_own_means_no_highlights() -> None:
    """Setting a list, even an empty one, replaces the parent's."""
    parent = _schema("condition", highlights={"card": [{"key": "condition"}]})
    own = _schema("width", highlights={"card": []})

    result = effective_schema(parent, own)

    assert result is not None
    assert result["x-menagerist"]["highlights"]["card"] == []


def test_the_subtypes_other_settings_win_and_the_parents_fill_gaps() -> None:
    """Root keys and the version come from the subtype, else the parent."""
    parent = _schema("condition", version=2)
    parent["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    own = _schema("width")
    own["additionalProperties"] = False

    result = effective_schema(parent, own)

    assert result is not None
    assert result["$schema"] == parent["$schema"]
    assert result["additionalProperties"] is False
    assert result["x-menagerist"]["version"] == 2


def test_the_inputs_are_not_changed() -> None:
    """Combining never edits either stored schema."""
    parent = _schema("condition", required=["condition"], layout=[{"title": "P"}])
    own = _schema("width", required=["width"], layout=[{"title": "S"}])
    before = copy.deepcopy((parent, own))

    effective_schema(parent, own)

    assert (parent, own) == before


def test_a_key_both_define_keeps_the_parents_definition() -> None:
    """The rules refuse this, so it only guards stored data that predates them."""
    parent = _schema("condition")
    own = _schema("condition")
    own["properties"]["condition"]["title"] = "Mine"

    result = effective_schema(parent, own)

    assert result is not None
    assert result["properties"]["condition"]["title"] == "Condition"

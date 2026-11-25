"""Planning what attaching or detaching a parent does to a type's fields (#775)."""

import copy
from typing import Any

from app.modules.graph.application.parent_change import (
    ParentChange,
    ParentChangeResult,
    plan_parent_change,
)
from app.modules.graph.application.schema_meta import effective_schema


def _text(title: str) -> dict[str, Any]:
    return {"type": "string", "title": title}


def _choice(title: str, *options: str) -> dict[str, Any]:
    return {
        "type": "string",
        "title": title,
        "enum": list(options),
        "x-menagerist": {"kind": "choice"},
    }


def _schema(
    props: dict[str, dict[str, Any]],
    *,
    required: list[str] | None = None,
    layout: list[Any] | None = None,
    highlights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    meta: dict[str, Any] = {}
    if required is not None:
        meta["required"] = required
    if layout is not None:
        meta["layout"] = layout
    if highlights is not None:
        meta["highlights"] = highlights
    if meta:
        schema["x-menagerist"] = meta
    return schema


def _plan(
    own: dict[str, Any] | None,
    *,
    old: tuple[str, dict[str, Any]] | None = None,
    new: tuple[str, dict[str, Any]] | None = None,
    change: ParentChange | None = None,
) -> ParentChangeResult:
    return plan_parent_change(
        old_slug=old[0] if old else None,
        old_parent=old[1] if old else None,
        new_slug=new[0] if new else None,
        new_parent=new[1] if new else None,
        own=own,
        change=change or ParentChange(),
    )


def _own(result: ParentChangeResult) -> dict[str, Any]:
    assert result.own_schema is not None
    return result.own_schema


def _parent(result: ParentChangeResult) -> dict[str, Any]:
    assert result.parent_schema is not None
    return result.parent_schema


MEMORABILIA = _schema(
    {"condition": _choice("Condition", "Mint", "Good"), "value": _text("Value")},
    required=["condition"],
    layout=[{"key": "condition"}, {"key": "value"}],
    highlights={"card": [{"key": "condition"}]},
)
POSTER = _schema({"width": _text("Width")}, layout=[{"key": "width"}])


def test_no_parent_before_or_after_changes_nothing() -> None:
    """A top-level type left top-level keeps its fields."""
    result = _plan(POSTER)

    assert result.own_schema == POSTER
    assert (result.merged, result.conflicts, result.kept, result.archived) == ((),) * 4
    assert result.parent_schema is None


def test_attaching_with_no_clash_leaves_the_fields_as_they_are() -> None:
    """Different keys just sit side by side."""
    result = _plan(POSTER, new=("memorabilia", MEMORABILIA))

    assert result.own_schema == POSTER
    assert result.clashes == ()
    assert result.parent_schema is None


def test_attaching_a_type_with_no_fields_of_its_own() -> None:
    """A type with no schema attaches cleanly."""
    result = _plan(None, new=("memorabilia", MEMORABILIA))

    assert result.own_schema is None
    assert result.clashes == ()


def test_a_same_kind_clash_is_reported_and_left_when_refusing() -> None:
    """By default nothing is merged: the clash is only named."""
    own = _schema({"condition": _choice("Condition", "Mint", "Worn")})

    result = _plan(own, new=("memorabilia", MEMORABILIA))

    assert result.clashes == ("condition",)
    assert result.merged == ()
    assert result.own_schema == own
    assert result.parent_schema is None


def test_merging_drops_the_subtypes_field_and_widens_the_parents_options() -> None:
    """The parent's definition is used, with every option either side listed."""
    own = _schema(
        {"condition": _choice("Condition", "Mint", "Worn"), "width": _text("Width")},
        required=["condition", "width"],
        layout=[{"key": "condition"}, {"key": "width"}],
    )

    result = _plan(
        own,
        new=("memorabilia", MEMORABILIA),
        change=ParentChange(on_clash="merge"),
    )

    assert result.merged == ("condition",)
    assert list(_own(result)["properties"]) == ["width"]
    assert _own(result)["x-menagerist"]["required"] == ["width"]
    assert _own(result)["x-menagerist"]["layout"] == [{"key": "width"}]
    widened = _parent(result)["properties"]["condition"]["enum"]
    assert widened == ["Mint", "Good", "Worn"]
    # The parent's other fields and settings are untouched.
    assert _parent(result)["x-menagerist"] == MEMORABILIA["x-menagerist"]


def test_a_different_kind_clash_blocks_even_when_merging() -> None:
    """The same key as another kind of field cannot be merged."""
    own = _schema({"condition": {"type": "number", "title": "Condition"}})

    result = _plan(
        own,
        new=("memorabilia", MEMORABILIA),
        change=ParentChange(on_clash="merge"),
    )

    assert result.conflicts == ("condition",)
    assert result.merged == ()
    assert result.own_schema == own


def test_merging_removes_the_field_from_a_json_schema_required_list() -> None:
    """The standard `required` list loses the merged key, and goes if it empties."""
    kept = {
        **_schema({"condition": _choice("Condition", "Mint"), "width": _text("W")}),
        "required": ["condition", "width"],
    }
    emptied = {
        **_schema({"condition": _choice("Condition", "Mint")}),
        "required": ["condition"],
    }
    change = ParentChange(on_clash="merge")

    first = _plan(kept, new=("memorabilia", MEMORABILIA), change=change)
    second = _plan(emptied, new=("memorabilia", MEMORABILIA), change=change)

    assert _own(first)["required"] == ["width"]
    assert "required" not in _own(second)


def test_merging_prunes_a_section_that_listed_the_merged_field() -> None:
    """A field gone from the subtype leaves no dangling place in its layout."""
    own = _schema(
        {"condition": _choice("Condition", "Mint"), "width": _text("Width")},
        layout=[
            {"id": "s1", "section": "Size", "items": [{"key": "width"}]},
            {"id": "s2", "section": "State", "items": [{"key": "condition"}]},
        ],
    )

    result = _plan(
        own,
        new=("memorabilia", MEMORABILIA),
        change=ParentChange(on_clash="merge"),
    )

    layout = _own(result)["x-menagerist"]["layout"]
    assert [s["section"] for s in layout] == ["Size", "State"]
    assert layout[1]["items"] == []


def test_detaching_with_keep_copies_the_parents_fields_onto_the_type() -> None:
    """Nothing disappears: the type now defines what it used to inherit."""
    result = _plan(POSTER, old=("memorabilia", MEMORABILIA))

    assert result.own_schema == effective_schema(MEMORABILIA, POSTER)
    assert result.kept == ("condition", "value")
    assert result.archived == ()
    # The effective settings come along too.
    assert _own(result)["x-menagerist"]["required"] == ["condition"]
    assert (
        _own(result)["x-menagerist"]["highlights"]
        == MEMORABILIA["x-menagerist"]["highlights"]
    )


def test_detaching_with_drop_archives_the_parents_fields_on_the_type() -> None:
    """The fields are hidden, not deleted, so values stay and can be restored."""
    result = _plan(
        POSTER, old=("memorabilia", MEMORABILIA), change=ParentChange(on_detach="drop")
    )

    props = _own(result)["properties"]
    assert list(props) == ["width", "condition", "value"]
    assert props["condition"]["x-menagerist"]["archived"] is True
    assert props["condition"]["enum"] == ["Mint", "Good"]
    assert "x-menagerist" not in props["width"]
    assert result.archived == ("condition", "value")
    assert result.kept == ()
    # Archived fields are neither required nor placed.
    assert "required" not in _own(result).get("x-menagerist", {})
    assert _own(result)["x-menagerist"]["layout"] == [{"key": "width"}]


def test_dropping_leaves_a_field_the_type_already_has_alone() -> None:
    """A key the type defines keeps its own definition."""
    own = _schema({"condition": _text("State")})

    result = _plan(
        own, old=("memorabilia", MEMORABILIA), change=ParentChange(on_detach="drop")
    )

    assert _own(result)["properties"]["condition"] == _text("State")
    assert result.archived == ("value",)


def test_moving_to_another_parent_detaches_then_attaches() -> None:
    """Fields kept from the old parent clash with the new one's, and merge."""
    merchandise = _schema({"condition": _choice("Condition", "New")})

    result = _plan(
        POSTER,
        old=("memorabilia", MEMORABILIA),
        new=("merchandise", merchandise),
        change=ParentChange(on_clash="merge"),
    )

    assert result.kept == ("condition", "value")
    assert result.merged == ("condition",)
    assert list(_own(result)["properties"]) == ["value", "width"]
    assert _parent(result)["properties"]["condition"]["enum"] == [
        "New",
        "Mint",
        "Good",
    ]


def test_moving_with_a_clash_and_refusing_reports_it() -> None:
    """Without merge the shared key stops the move."""
    merchandise = _schema({"condition": _choice("Condition", "New")})

    result = _plan(
        POSTER, old=("memorabilia", MEMORABILIA), new=("merchandise", merchandise)
    )

    assert result.clashes == ("condition",)
    assert result.merged == ()


def test_staying_under_the_same_parent_changes_nothing() -> None:
    """Naming the parent it already has is not a move."""
    result = _plan(
        POSTER,
        old=("memorabilia", MEMORABILIA),
        new=("memorabilia", MEMORABILIA),
        change=ParentChange(on_clash="merge", on_detach="drop"),
    )

    assert result.own_schema == POSTER
    assert (result.merged, result.kept, result.archived) == ((),) * 3


def test_planning_never_changes_its_inputs() -> None:
    """The plan works on copies of both schemas."""
    own = _schema({"condition": _choice("Condition", "Worn")}, required=["condition"])
    before = copy.deepcopy((own, MEMORABILIA))

    _plan(
        own,
        old=("memorabilia", MEMORABILIA),
        new=("memorabilia-2", MEMORABILIA),
        change=ParentChange(on_clash="merge", on_detach="keep"),
    )

    assert (own, MEMORABILIA) == before


def test_attach_then_detach_with_keep_returns_to_the_same_fields() -> None:
    """Round trip: what the subtype uses is the same after attaching and detaching."""
    own = _schema(
        {"condition": _choice("Condition", "Mint", "Worn"), "width": _text("Width")},
        required=["width"],
    )
    attached = _plan(
        own, new=("memorabilia", MEMORABILIA), change=ParentChange(on_clash="merge")
    )
    used_attached = effective_schema(attached.parent_schema, attached.own_schema)

    detached = _plan(
        attached.own_schema,
        old=("memorabilia", _parent(attached)),
        change=ParentChange(on_detach="keep"),
    )

    assert used_attached is not None
    assert detached.own_schema is not None
    assert set(_own(detached)["properties"]) == set(used_attached["properties"])
    assert _own(detached)["properties"]["condition"]["enum"] == [
        "Mint",
        "Good",
        "Worn",
    ]
    # Every field the subtype could be asked for before is still defined.
    assert set(_own(detached)["properties"]) >= set(own["properties"])

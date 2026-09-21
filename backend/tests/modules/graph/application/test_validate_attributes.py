import pytest

from app.modules.graph.application._validate_attributes import validate_attributes
from app.modules.graph.domain.errors import InvalidAttributesError

_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "year": {"title": "Year", "type": "number"},
        "title": {"title": "Title", "type": "string"},
    },
    "required": ["year"],
}


async def test_validate_attributes_passes_on_valid_data() -> None:
    """No exception raised when attributes satisfy the schema."""
    validate_attributes(_SCHEMA, {"year": 1979, "title": "Alien"})


async def test_validate_attributes_raises_with_per_field_errors() -> None:
    """InvalidAttributesError carries path + message for each violation."""
    with pytest.raises(InvalidAttributesError) as exc_info:
        validate_attributes(_SCHEMA, {"year": "not-a-number"})

    errors = exc_info.value.validation_errors
    assert len(errors) >= 1
    year_error = next(e for e in errors if e["path"] == "/year")
    assert "number" in year_error["message"]


async def test_validate_attributes_collects_multiple_errors() -> None:
    """All violations are collected, not just the first."""
    with pytest.raises(InvalidAttributesError) as exc_info:
        validate_attributes(_SCHEMA, {"year": "x", "title": 5})

    paths = {e["path"] for e in exc_info.value.validation_errors}
    assert paths == {"/year", "/title"}


async def test_validate_attributes_ignores_root_required() -> None:
    """The root `required` array is advisory and never rejects attributes."""
    validate_attributes(_SCHEMA, {})


async def test_validate_attributes_ignores_archived_properties() -> None:
    """An archived property no longer validates its value."""
    schema = {
        "type": "object",
        "properties": {
            "year": {
                "type": "number",
                "x-menagerist": {"archived": True},
            }
        },
    }
    validate_attributes(schema, {"year": "not-a-number"})


_STALE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["Draft", "Published"]},
        "year": {"type": "number"},
        "cast": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"qty": {"type": "number"}},
            },
        },
    },
}


async def test_validate_attributes_ignores_unchanged_invalid_key_on_update() -> None:
    """A stale invalid value that is not being edited does not block the save."""
    previous = {"status": "Archived", "year": 1979}

    validate_attributes(
        _STALE_SCHEMA, {"status": "Archived", "year": 1980}, previous=previous
    )


async def test_validate_attributes_reports_changed_invalid_key_on_update() -> None:
    """Editing the invalid field to another invalid value still errors."""
    previous = {"status": "Archived"}

    with pytest.raises(InvalidAttributesError) as exc_info:
        validate_attributes(_STALE_SCHEMA, {"status": "Gone"}, previous=previous)

    assert [e["path"] for e in exc_info.value.validation_errors] == ["/status"]


async def test_validate_attributes_passes_changed_valid_key_on_update() -> None:
    """Changing a stale value to a valid one passes."""
    validate_attributes(
        _STALE_SCHEMA, {"status": "Draft"}, previous={"status": "Archived"}
    )


async def test_validate_attributes_compares_group_values_deeply() -> None:
    """An unchanged invalid group is ignored; an edited one is reported."""
    stale = {"cast": [{"qty": "many"}]}

    validate_attributes(_STALE_SCHEMA, {"cast": [{"qty": "many"}]}, previous=stale)
    with pytest.raises(InvalidAttributesError) as exc_info:
        validate_attributes(_STALE_SCHEMA, {"cast": [{"qty": "lots"}]}, previous=stale)

    assert exc_info.value.validation_errors[0]["path"] == "/cast/0/qty"


async def test_validate_attributes_treats_true_and_one_as_different() -> None:
    """Type-strict comparison: 1 -> True is a change and is validated."""
    with pytest.raises(InvalidAttributesError):
        validate_attributes(_STALE_SCHEMA, {"year": True}, previous={"year": 1})


async def test_validate_attributes_always_reports_root_level_errors() -> None:
    """An error against the whole object is kept even when previous is equal."""
    schema = {"type": "object", "minProperties": 2}

    with pytest.raises(InvalidAttributesError):
        validate_attributes(schema, {"a": 1}, previous={"a": 1})


async def test_validate_attributes_without_previous_validates_everything() -> None:
    """Create keeps full validation."""
    with pytest.raises(InvalidAttributesError):
        validate_attributes(_STALE_SCHEMA, {"status": "Archived"})

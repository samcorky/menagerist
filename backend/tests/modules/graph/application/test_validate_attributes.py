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

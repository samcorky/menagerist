import pytest

from app.modules.graph.application.extra_schema_limits import (
    MAX_EXTRA_SCHEMA_FIELDS,
    check_extra_schema_limits,
)
from app.modules.graph.domain.errors import InvalidSchemaError


def _schema(count: int) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            f"field_{i}": {"title": f"Field {i}", "type": "string"}
            for i in range(count)
        },
    }


def test_none_overlay_is_fine() -> None:
    """None overlay is always allowed."""
    check_extra_schema_limits(None)


def test_overlay_under_the_limit_is_fine() -> None:
    """Overlay with exactly the maximum allowed fields is fine."""
    check_extra_schema_limits(_schema(MAX_EXTRA_SCHEMA_FIELDS))


def test_overlay_over_the_limit_raises() -> None:
    """Overlay with too many fields raises InvalidSchemaError."""
    with pytest.raises(InvalidSchemaError):
        check_extra_schema_limits(_schema(MAX_EXTRA_SCHEMA_FIELDS + 1))


def test_an_already_over_limit_overlay_is_not_re_rejected_if_it_did_not_grow() -> None:
    """A node saved before the limit existed.

    Edited without adding fields, still saves.
    """
    over_limit = _schema(MAX_EXTRA_SCHEMA_FIELDS + 5)
    check_extra_schema_limits(over_limit, previous=over_limit)


def test_growing_past_the_limit_from_an_already_large_overlay_raises() -> None:
    """Growing past the limit from an already large overlay raises."""
    previous = _schema(MAX_EXTRA_SCHEMA_FIELDS + 5)
    grown = _schema(MAX_EXTRA_SCHEMA_FIELDS + 6)
    with pytest.raises(InvalidSchemaError):
        check_extra_schema_limits(grown, previous=previous)

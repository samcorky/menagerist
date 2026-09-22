from typing import Any

from app.modules.graph.domain.errors import InvalidSchemaError

MAX_EXTRA_SCHEMA_FIELDS = 50


def _property_count(schema: dict[str, Any] | None) -> int:
    properties = schema.get("properties") if schema else None
    return len(properties) if isinstance(properties, dict) else 0


def check_extra_schema_limits(
    extra_schema: dict[str, Any] | None,
    *,
    previous: dict[str, Any] | None = None,
) -> None:
    """Check a node's `extra_schema` overlay does not have too many fields.

    Only rejects a *growing* overlay: an item that already exceeds the limit
    (saved before the limit existed, or otherwise) can still be edited as
    long as it does not gain more fields.

    :raises InvalidSchemaError: when the overlay has grown past the limit.
    """
    count = _property_count(extra_schema)
    previous_count = _property_count(previous)
    if count > MAX_EXTRA_SCHEMA_FIELDS and count > previous_count:
        raise InvalidSchemaError(
            f"An item can have at most {MAX_EXTRA_SCHEMA_FIELDS} extra fields."
        )

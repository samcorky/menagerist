from typing import Any

from app.modules.graph.domain.errors import InvalidAttributesError

MAX_CUSTOM_NAME_LENGTH = 100
MAX_CUSTOM_DETAILS = 50

_KEYWORD = "customDetail"


def _defined_keys(schema: dict[str, Any] | None) -> set[str]:
    properties = schema.get("properties") if schema else None
    return set(properties) if isinstance(properties, dict) else set()


def _name_problem(key: str) -> str | None:
    if key.strip() == "" or key != key.strip():
        return "Detail names cannot be blank or start or end with spaces."
    if len(key) > MAX_CUSTOM_NAME_LENGTH:
        return f"Detail names can be at most {MAX_CUSTOM_NAME_LENGTH} characters."
    return None


def check_custom_details(
    schema: dict[str, Any] | None,
    attributes: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
) -> None:
    """Check the per-item details that the type's schema does not define.

    Only names that are new compared with `previous` are checked, and the count
    only when it grows past the limit, so an existing item that already breaks
    a rule can still be edited. Keys the schema defines (archived ones
    included) are never custom.

    :raises InvalidAttributesError: with a `customDetail` keyword per problem.
    """
    defined = _defined_keys(schema)
    previous = previous or {}
    custom = [key for key in attributes if key not in defined]
    errors: list[dict[str, Any]] = [
        {
            "path": "/" + key,
            "message": problem,
            "keyword": _KEYWORD,
            "value": key,
        }
        for key in custom
        if key not in previous and (problem := _name_problem(key)) is not None
    ]
    previous_count = sum(1 for key in previous if key not in defined)
    if len(custom) > MAX_CUSTOM_DETAILS and len(custom) > previous_count:
        errors.append(
            {
                "path": "/",
                "message": (
                    f"An item can have at most {MAX_CUSTOM_DETAILS} extra details."
                ),
                "keyword": _KEYWORD,
                "value": MAX_CUSTOM_DETAILS,
            }
        )
    if errors:
        raise InvalidAttributesError(errors)

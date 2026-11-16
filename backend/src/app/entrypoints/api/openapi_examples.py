"""Give each success response the example of the model it returns.

Response models carry their example in `json_schema_extra`, which lands on the
component schema. Clients and the IBM lint read examples on the response itself,
so each 2xx body without one gets its model's first example, wrapped in a list
for a list route, and an unnamed list schema gets a description naming its items.
"""

import copy
from typing import Any

_REF_PREFIX = "#/components/schemas/"


def _ref_name(schema: dict[str, Any]) -> str | None:
    ref = schema.get("$ref")
    return ref.removeprefix(_REF_PREFIX) if isinstance(ref, str) else None


def _example_for(schema: dict[str, Any], schemas: dict[str, Any]) -> object | None:
    """The example of `schema`'s model, a list of one for an array, or None."""
    if name := _ref_name(schema):
        examples = schemas.get(name, {}).get("examples")
        return copy.deepcopy(examples[0]) if examples else None
    if schema.get("type") == "array":
        item = _example_for(schema.get("items", {}), schemas)
        return None if item is None else [item]
    return None


def _describe_list(schema: dict[str, Any]) -> None:
    name = _ref_name(schema.get("items", {}))
    if schema.get("type") == "array" and name and not schema.get("description"):
        schema["description"] = f"Each entry is a `{name}`."


def _fill_response(response: dict[str, Any], schemas: dict[str, Any]) -> None:
    for media in response.get("content", {}).values():
        schema = media.get("schema", {})
        _describe_list(schema)
        if "example" not in media and "examples" not in media:
            example = _example_for(schema, schemas)
            if example is not None:
                media["example"] = example


def add_success_examples(openapi_schema: dict[str, Any]) -> None:
    """Fill in each 2xx body's example from its model, keeping any it has."""
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    for item in openapi_schema.get("paths", {}).values():
        for operation in item.values():
            responses = (
                operation.get("responses", {}) if isinstance(operation, dict) else {}
            )
            for status, response in responses.items():
                if str(status).startswith("2"):
                    _fill_response(response, schemas)

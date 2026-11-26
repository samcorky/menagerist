"""A list's `sort` keys are names of fields in the rows it returns.

The list convention (docs/API_STYLE.md) lets a client sort by what it sees, so
every value a route's `sort` accepts must be a property of that route's response
item.
"""

from typing import Any

import pytest

from app.entrypoints.api import create_app


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        node = schema["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
    return node


def _enum_values(schema: dict[str, Any], node: dict[str, Any]) -> set[str]:
    """The values of an enum parameter, whether optional (`anyOf` null) or not."""
    node = _resolve(schema, node)
    values: set[str] = set(node.get("enum", ()))
    for option in node.get("anyOf", ()):
        values |= _enum_values(schema, option)
    return values


def sort_key_errors(schema: dict[str, Any]) -> list[str]:
    """Each `sort` value that is not a field of its route's response rows."""
    errors: list[str] = []
    for path, item in schema["paths"].items():
        operation = item.get("get")
        if operation is None:
            continue
        sort = next(
            (p for p in operation.get("parameters", ()) if p["name"] == "sort"), None
        )
        if sort is None:
            continue
        body = operation["responses"]["200"]["content"]["application/json"]["schema"]
        rows = _resolve(schema, _resolve(schema, body).get("items", {}))
        fields = set(rows.get("properties", ()))
        errors.extend(
            f"GET {path}: sort={value} is not a field of the response"
            for value in sorted(_enum_values(schema, sort["schema"]) - fields)
        )
    return errors


@pytest.mark.fast
def test_every_sort_key_is_a_field_of_the_rows_returned() -> None:
    """Holds for every list route in the app's own schema."""
    assert sort_key_errors(create_app().openapi()) == []


def _schema(sort_values: list[str]) -> dict[str, Any]:
    return {
        "paths": {
            "/rows": {
                "get": {
                    "parameters": [
                        {
                            "name": "sort",
                            "in": "query",
                            "schema": {
                                "anyOf": [
                                    {"$ref": "#/components/schemas/RowSort"},
                                    {"type": "null"},
                                ]
                            },
                        }
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Row"},
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "RowSort": {"enum": sort_values, "type": "string"},
                "Row": {"properties": {"name": {}, "created_at": {}}},
            }
        },
    }


@pytest.mark.fast
def test_a_sort_key_that_is_not_a_response_field_is_reported() -> None:
    """The check catches the mistake it is for, not only passing on today's routes."""
    assert sort_key_errors(_schema(["name", "created_at"])) == []
    assert sort_key_errors(_schema(["name", "colour"])) == [
        "GET /rows: sort=colour is not a field of the response"
    ]

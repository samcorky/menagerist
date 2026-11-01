"""An open-ended map body must carry its own example.

Swagger renders a schema that is only `additionalProperties` as `additionalProp1`,
which tells a reader nothing. Give such a body an explicit example.
"""

from typing import Any

from app.entrypoints.api import create_app

# Operations whose open-ended body has no useful example, with the reason.
ALLOWED: dict[str, str] = {}


def _resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        node: Any = spec
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        schema = node
    return schema


def _is_open_map(spec: dict[str, Any], schema: dict[str, Any]) -> bool:
    resolved = _resolve(spec, schema)
    return bool(resolved.get("additionalProperties")) and not resolved.get("properties")


def _media_types(spec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            where = f"{method.upper()} {path}"
            body = op.get("requestBody", {}).get("content", {}).get("application/json")
            if body:
                found.append((f"{where} request", body))
            for status, response in op.get("responses", {}).items():
                media = response.get("content", {}).get("application/json")
                if media and status.startswith("2"):
                    found.append((f"{where} {status}", media))
    return found


def test_open_ended_json_bodies_have_an_explicit_example() -> None:
    """A map-shaped request or success body names an example, not additionalProp1."""
    spec = create_app().openapi()
    offenders = [
        name
        for name, media in _media_types(spec)
        if _is_open_map(spec, media.get("schema", {}))
        and "example" not in media
        and "examples" not in media
        and not _resolve(spec, media["schema"]).get("examples")
        and name.rsplit(" ", 1)[0] not in ALLOWED
    ]
    assert offenders == []


def test_the_allowlist_is_current() -> None:
    """An allowed operation must still exist."""
    spec = create_app().openapi()
    known = {name.rsplit(" ", 1)[0] for name, _ in _media_types(spec)}
    assert set(ALLOWED) <= known

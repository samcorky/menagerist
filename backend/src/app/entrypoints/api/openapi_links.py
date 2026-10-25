"""Add OpenAPI `links` that carry an id from one response into the next call.

Convention: a collection path (`/node`) and its item paths (`/node/{node_id}`,
`/node/{node_id}/restore`). A create or list on the collection, or a read or
update on the item itself, returns the id the item paths take. Each such
success response links to the other operations under the item path, mapping the
id with a `$response.body#/...` runtime expression. Paths the convention does
not fit (several path parameters, no collection operation) get no generated
link; routes can still declare their own, which are never overwritten.
"""

import re
from typing import Any

_ITEM_PATH = re.compile(r"^(?P<collection>.*)/\{(?P<param>\w+)\}(?P<rest>(/[\w-]+)*)$")
_METHODS = ("get", "post", "put", "patch", "delete")
_JSON = "application/json"


def _resolve(openapi: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        node = openapi["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
    return node


def _id_pointer(
    openapi: dict[str, Any], response: dict[str, Any], *, allow_list: bool
) -> str | None:
    """Return the pointer to the id in a JSON body, or None if it has none."""
    schema = response.get("content", {}).get(_JSON, {}).get("schema")
    if schema is None:
        return None
    schema = _resolve(openapi, schema)
    prefix = ""
    if schema.get("type") == "array":
        if not allow_list:
            return None
        schema = _resolve(openapi, schema["items"])
        prefix = "/0"
    return f"{prefix}/id" if "id" in schema.get("properties", {}) else None


def _words(operation_id: str) -> str:
    return operation_id.replace("_", " ").capitalize()


def _link_name(operation_id: str) -> str:
    return "".join(word.capitalize() for word in operation_id.split("_"))


def _operations(path_item: dict[str, Any]) -> list[dict[str, Any]]:
    return [path_item[method] for method in _METHODS if method in path_item]


def add_conventional_links(openapi: dict[str, Any]) -> None:
    """Attach generated `links` to the success responses that return an id."""
    paths: dict[str, dict[str, Any]] = openapi["paths"]
    targets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for path, item in paths.items():
        match = _ITEM_PATH.match(path)
        if match and "{" not in match["collection"] + match["rest"]:
            key = (match["collection"], match["param"])
            targets.setdefault(key, []).extend(_operations(item))

    for (collection, param), operations in targets.items():
        if collection not in paths:
            continue
        for source in _operations(paths[collection]):
            _link_source(openapi, source, param, operations, allow_list=True)
        for source in _operations(paths.get(f"{collection}/{{{param}}}", {})):
            _link_source(openapi, source, param, operations, allow_list=False)


def _link_source(
    openapi: dict[str, Any],
    source: dict[str, Any],
    param: str,
    targets: list[dict[str, Any]],
    *,
    allow_list: bool,
) -> None:
    for status, response in source["responses"].items():
        if status[0] != "2":
            continue
        pointer = _id_pointer(openapi, response, allow_list=allow_list)
        if pointer is None:
            continue
        links = response.get("links", {})
        taken = {link["operationId"] for link in links.values()}
        for target in targets:
            operation_id = target["operationId"]
            if operation_id == source["operationId"] or operation_id in taken:
                continue
            links.setdefault(
                _link_name(operation_id),
                {
                    "operationId": operation_id,
                    "parameters": {param: f"$response.body#{pointer}"},
                    "description": (
                        f"{_words(operation_id)} with the id from this response."
                    ),
                },
            )
        if links:
            response["links"] = links

from typing import TYPE_CHECKING, Any

from fastapi.openapi.utils import get_openapi

if TYPE_CHECKING:
    from fastapi import FastAPI

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "Nodes",
        "description": "Endpoints for managing nodes in the graph.",
    },
    {
        "name": "Edges",
        "description": "Endpoints for managing edges in the graph.",
    },
    {
        "name": "Node Types",
        "description": "Endpoints for managing node types in the graph.",
    },
    {
        "name": "Edge Types",
        "description": "Endpoints for managing edge types in the graph.",
    },
    {
        "name": "System",
        "description": "System-level endpoints for health checks and diagnostics.",
    },
    {
        "name": "Media",
        "description": "Endpoints for managing media assets.",
    },
    {
        "name": "Presets",
        "description": "Endpoints for managing presets.",
    },
    {
        "name": "v1",
        "description": "Version 1 of the API.",
    },
]


def _rewrite_refs(node: object, renamed_refs: dict[str, str]) -> None:
    """Recursively rewrite `$ref` pointers throughout an OpenAPI schema tree."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref in renamed_refs:
            node["$ref"] = renamed_refs[ref]
        for value in node.values():
            _rewrite_refs(value, renamed_refs)
    elif isinstance(node, list):
        for item in node:
            _rewrite_refs(item, renamed_refs)


def _normalise_openapi_schemas(openapi_schema: dict[str, Any]) -> None:
    """Rename FastAPI's auto-generated `Body_<operation_id>` schemas.

    FastAPI synthesises a request-body model named ``Body_<operation_id>`` for
    any endpoint that combines a file upload with other form fields — there is
    no supported way to name that wrapper model per-endpoint (see
    `backend/README.md` for the underlying constraint). Rename it here instead,
    e.g. ``Body_upload_and_attach_media`` -> ``UploadAndAttachMediaBody``.
    """
    components = openapi_schema.get("components", {}).get("schemas", {})
    renames = {
        name: "".join(word.capitalize() for word in name.split("_")[1:]) + "Body"
        for name in list(components)
        if name.startswith("Body_")
    }
    if not renames:
        return
    for old_name, new_name in renames.items():
        schema = components.pop(old_name)
        schema["title"] = new_name
        components[new_name] = schema
    renamed_refs = {
        f"#/components/schemas/{old_name}": f"#/components/schemas/{new_name}"
        for old_name, new_name in renames.items()
    }
    _rewrite_refs(openapi_schema, renamed_refs)

    openapi_schema["components"]["schemas"] = dict(sorted(components.items()))


def configure_openapi(app: FastAPI) -> None:
    """Attach customised OpenAPI schema generation and tag metadata."""
    app.openapi_tags = OPENAPI_TAGS

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
            servers=app.servers,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
            summary=app.summary,
        )
        openapi_schema["info"]["x-logo"] = {
            "url": "/api/docs/logo.svg",
            "altText": f"{app.title} logo",
        }
        _normalise_openapi_schemas(openapi_schema)
        app.openapi_schema = openapi_schema
        return openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

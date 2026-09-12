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
        "name": "v1",
        "description": "Version 1 of the API.",
    },
]


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
        app.openapi_schema = openapi_schema
        return openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

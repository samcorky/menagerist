from fastapi import APIRouter, FastAPI
from granian.utils.proxies import wrap_asgi_with_proxy_headers
from starlette.middleware.cors import CORSMiddleware

from app.entrypoints.api.shared.problem_response import register_exception_handlers
from app.entrypoints.api.shared.request_context_middleware import (
    RequestContextMiddleware,
)
from app.entrypoints.api.shared.version_header import VersionHeaderMiddleware
from app.entrypoints.api.system.router import router as system_router
from app.modules.graph.adapters.api.edge.router import router as edge_router
from app.modules.graph.adapters.api.edge_type.router import router as edge_type_router
from app.modules.graph.adapters.api.node.router import router as graph_router
from app.modules.graph.adapters.api.node_type.router import router as node_type_router
from app.platform.app_info import load_app_info
from app.platform.config import get_api_settings
from app.platform.logging_config import configure_logging

configure_logging()

api_router = APIRouter(prefix="/api")
api_router.include_router(system_router)

api_v1_router = APIRouter(prefix="/v1", tags=["v1"])
api_v1_router.include_router(graph_router)
api_v1_router.include_router(edge_router)
api_v1_router.include_router(node_type_router)
api_v1_router.include_router(edge_type_router)

api_router.include_router(api_v1_router)


def create_app() -> FastAPI:
    """Create an instance of the API cli_app."""
    app_info = load_app_info()
    fastapi_app = FastAPI(
        title=app_info.name,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    fastapi_app.version = app_info.version
    if app_info.project.description:
        fastapi_app.description = app_info.project.description

    # noinspection PyTypeChecker
    fastapi_app.add_middleware(VersionHeaderMiddleware)
    # noinspection PyTypeChecker
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=get_api_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["App-Version"],
    )
    fastapi_app.add_middleware(
        RequestContextMiddleware,
    )

    fastapi_app.include_router(api_router)
    register_exception_handlers(fastapi_app)

    fastapi_app.openapi_tags = [
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
            "name": "v1",
            "description": "Version 1 of the API.",
        },
    ]

    return fastapi_app


app = wrap_asgi_with_proxy_headers(create_app(), trusted_hosts="*")

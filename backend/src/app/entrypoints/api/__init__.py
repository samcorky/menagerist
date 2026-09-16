from fastapi import APIRouter, FastAPI
from granian.utils.proxies import wrap_asgi_with_proxy_headers
from starlette.middleware.cors import CORSMiddleware

from app.entrypoints.api.docs.router import router as docs_router
from app.entrypoints.api.openapi import configure_openapi
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.entrypoints.api.shared.problem_response import register_exception_handlers
from app.entrypoints.api.shared.request_context_middleware import (
    RequestContextMiddleware,
)
from app.entrypoints.api.shared.security_headers import SecurityHeadersMiddleware
from app.entrypoints.api.shared.version_header import VersionHeaderMiddleware
from app.modules.graph.adapters.api.edge.router import router as edge_router
from app.modules.graph.adapters.api.edge_type.router import router as edge_type_router
from app.modules.graph.adapters.api.node.router import router as graph_router
from app.modules.graph.adapters.api.node_type.router import router as node_type_router
from app.modules.media.adapters.api.media.router import router as media_router
from app.modules.system.adapters.api.router import router as system_router
from app.platform.app_info import load_app_info
from app.platform.config import get_api_settings
from app.platform.logging_config import configure_logging

configure_logging()

api_router = APIRouter(prefix="/api", route_class=PermissionAwareRoute)
api_router.include_router(system_router)
api_router.include_router(docs_router)

api_v1_router = APIRouter(prefix="/v1", route_class=PermissionAwareRoute, tags=["v1"])
api_v1_router.include_router(graph_router)
api_v1_router.include_router(edge_router)
api_v1_router.include_router(node_type_router)
api_v1_router.include_router(edge_type_router)
api_v1_router.include_router(media_router)

api_router.include_router(api_v1_router)


def create_app() -> FastAPI:
    """Create an instance of the API cli_app."""
    app_info = load_app_info()
    license_info: dict[str, str] = {}
    if app_info.project.license:
        license_info["name"] = app_info.project.license
    if app_info.license_url:
        # noinspection bad-index
        license_info["url"] = app_info.license_url

    fastapi_app = FastAPI(
        title=app_info.name,
        license_info=license_info or None,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    fastapi_app.version = app_info.version
    if app_info.project.description:
        fastapi_app.description = app_info.project.description

    # noinspection PyTypeChecker
    fastapi_app.add_middleware(SecurityHeadersMiddleware)
    # noinspection PyTypeChecker
    fastapi_app.add_middleware(VersionHeaderMiddleware)
    # noinspection PyTypeChecker
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=get_api_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["App-Version", "Total-Count", "Link"],
    )
    fastapi_app.add_middleware(
        RequestContextMiddleware,
    )

    fastapi_app.include_router(api_router)
    register_exception_handlers(fastapi_app)
    configure_openapi(fastapi_app)

    return fastapi_app


app = wrap_asgi_with_proxy_headers(create_app(), trusted_hosts="*")

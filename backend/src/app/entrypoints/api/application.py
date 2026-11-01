from fastapi import APIRouter, Depends, FastAPI, Security
from granian.utils.proxies import wrap_asgi_with_proxy_headers
from starlette.middleware.cors import CORSMiddleware

from app.entrypoints.api.docs.router import router as docs_router
from app.entrypoints.api.openapi import configure_openapi
from app.entrypoints.api.permissions_router import router as permissions_router
from app.entrypoints.api.shared.bridges.claim_existing_data import (
    get_claim_existing_data,
)
from app.entrypoints.api.shared.http.cors import (
    CORS_MAX_AGE_SECONDS,
    CORS_METHODS,
    CORS_REQUEST_HEADERS,
    CORS_RESPONSE_HEADERS,
)
from app.entrypoints.api.shared.http.csrf import verify_csrf
from app.entrypoints.api.shared.http.problem_response import register_exception_handlers
from app.entrypoints.api.shared.http.proxy_header_observer import ProxyHeaderObserver
from app.entrypoints.api.shared.http.public_origin_observer import PublicOriginObserver
from app.entrypoints.api.shared.http.request_context_middleware import (
    RequestContextMiddleware,
)
from app.entrypoints.api.shared.http.security_headers import SecurityHeadersMiddleware
from app.entrypoints.api.shared.http.upload_limit_middleware import (
    UploadLimitMiddleware,
)
from app.entrypoints.api.shared.http.version_header import VersionHeaderMiddleware
from app.entrypoints.api.shared.permission_aware_route import cookie_scheme
from app.entrypoints.api.spa import SpaStaticFiles
from app.entrypoints.api.startup import lifespan
from app.modules.backup.adapters.api.router import (
    public_router as public_backup_router,
    router as backup_router,
)
from app.modules.backup.adapters.api.user_router import router as user_backup_router
from app.modules.collections.adapters.api.collection.router import (
    router as collection_router,
)
from app.modules.examples.adapters.api.example.router import router as example_router
from app.modules.graph.adapters.api.edge.router import router as edge_router
from app.modules.graph.adapters.api.edge_type.router import router as edge_type_router
from app.modules.graph.adapters.api.node.router import router as graph_router
from app.modules.graph.adapters.api.node_type.router import router as node_type_router
from app.modules.identity.adapters.api.auth_router import (
    public_router as public_auth_router,
    router as auth_router,
)
from app.modules.identity.adapters.api.dependencies import get_existing_data_claim
from app.modules.identity.adapters.api.session_router import router as session_router
from app.modules.identity.adapters.api.token_router import router as token_router
from app.modules.identity.adapters.api.user_router import router as user_router
from app.modules.media.adapters.api.media.router import router as media_router
from app.modules.presets.adapters.api.preset.router import router as preset_router
from app.modules.scheduling.adapters.api.router import router as scheduling_router
from app.modules.settings.adapters.api.router import router as settings_router
from app.modules.system.adapters.api.router import (
    probes_router as system_probes_router,
    public_router as public_system_router,
    router as system_router,
)
from app.platform.app_info import load_app_info
from app.platform.config import get_api_settings
from app.platform.logging_config import configure_logging

configure_logging()

# Each included router builds its own APIRoute instances at decoration time, so
# route_class here would never apply to them - every leaf router must be built
# with permission_aware_router() instead (see permission_aware_route.py).
api_router = APIRouter(prefix="/api")
api_router.include_router(system_probes_router)
api_router.include_router(docs_router)

# Every unsafe cookie-authenticated request here must come from this site's own
# pages (Sec-Fetch-Site / Origin); sign-in and
# first-run setup live on the public router below because no cookie exists yet.
api_v1_router = APIRouter(
    prefix="/v1",
    tags=["v1"],
    dependencies=[Depends(verify_csrf), Security(cookie_scheme)],
)
public_v1_router = APIRouter(prefix="/v1", tags=["v1"])
public_v1_router.include_router(public_auth_router)
public_v1_router.include_router(public_backup_router)
public_v1_router.include_router(public_system_router)
api_v1_router.include_router(backup_router)
api_v1_router.include_router(user_backup_router)
api_v1_router.include_router(graph_router)
api_v1_router.include_router(edge_router)
api_v1_router.include_router(node_type_router)
api_v1_router.include_router(edge_type_router)
api_v1_router.include_router(media_router)
api_v1_router.include_router(preset_router)
api_v1_router.include_router(scheduling_router)
api_v1_router.include_router(settings_router)
api_v1_router.include_router(example_router)
api_v1_router.include_router(collection_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(permissions_router)
api_v1_router.include_router(user_router)
api_v1_router.include_router(session_router)
api_v1_router.include_router(token_router)
api_v1_router.include_router(system_router)

api_router.include_router(api_v1_router)
api_router.include_router(public_v1_router)


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
        lifespan=lifespan,
    )
    fastapi_app.version = app_info.version
    if app_info.project.description:
        fastapi_app.summary = app_info.project.description

    # Innermost, so a 413 still gets the security, version and CORS headers.
    fastapi_app.add_middleware(UploadLimitMiddleware)
    # noinspection PyTypeChecker
    fastapi_app.add_middleware(SecurityHeadersMiddleware)
    # noinspection PyTypeChecker
    fastapi_app.add_middleware(VersionHeaderMiddleware)
    # noinspection PyTypeChecker
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=get_api_settings().cors_origins,
        allow_credentials=False,
        allow_methods=CORS_METHODS,
        allow_headers=CORS_REQUEST_HEADERS,
        expose_headers=CORS_RESPONSE_HEADERS,
        max_age=CORS_MAX_AGE_SECONDS,
    )
    fastapi_app.add_middleware(
        RequestContextMiddleware,
    )
    if (public_origin := get_api_settings().public_origin) is not None:
        fastapi_app.add_middleware(PublicOriginObserver, public_origin=public_origin)

    # Identity cannot import the other modules; this bridge supplies the claim.
    fastapi_app.dependency_overrides[get_existing_data_claim] = get_claim_existing_data
    fastapi_app.include_router(api_router)
    register_exception_handlers(fastapi_app)
    configure_openapi(fastapi_app)

    # Last, so every API route above wins; the SPA only sees what is left.
    if (frontend_dist_path := get_api_settings().frontend_dist_path) is not None:
        fastapi_app.mount("/", SpaStaticFiles(directory=frontend_dist_path), name="spa")

    return fastapi_app


app = ProxyHeaderObserver(
    wrap_asgi_with_proxy_headers(
        create_app(), trusted_hosts=get_api_settings().trusted_proxies
    ),
    trusted=get_api_settings().trusted_proxies,
)

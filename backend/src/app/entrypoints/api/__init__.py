from fastapi import APIRouter, FastAPI
from granian.utils.proxies import wrap_asgi_with_proxy_headers
from starlette.middleware.cors import CORSMiddleware

from app.entrypoints.api.system.router import router as system_router
from app.platform.app_info import load_app_info
from app.platform.logging_config import configure_logging

configure_logging()

api_router = APIRouter(prefix="/api")
api_router.include_router(system_router)


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
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    fastapi_app.include_router(api_router)

    return fastapi_app


app = wrap_asgi_with_proxy_headers(create_app(), trusted_hosts="*")

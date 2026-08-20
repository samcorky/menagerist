import structlog
from fastapi import APIRouter, FastAPI
from granian.utils.proxies import wrap_asgi_with_proxy_headers

from app.platform.app_info import load_app_info
from app.platform.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

api_router = APIRouter(prefix="/api")


def create_app() -> FastAPI:
    """Create an instance of the API app."""
    app_info = load_app_info()
    fastapi_app = FastAPI(
        title=app_info.name,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    if app_info.version:
        fastapi_app.version = app_info.version
    if app_info.project.description:
        fastapi_app.description = app_info.project.description

    fastapi_app.include_router(api_router)

    logger.info("API app created")

    return fastapi_app


app = wrap_asgi_with_proxy_headers(create_app(), trusted_hosts="*")

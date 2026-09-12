import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from app.platform.app_info import AppInfo, load_app_info

router = APIRouter()

_STATIC_DIR = Path(__file__).parent / "static"
_FAVICON_PATH = _STATIC_DIR / "favicon.svg"
_LOGO_PATH = _STATIC_DIR / "favicon.svg"

_STATIC_CACHE = "public, max-age=86400"


@router.get("/docs/favicon.svg", include_in_schema=False)
@router.get("/favicon.ico", include_in_schema=False)
def get_favicon() -> FileResponse:
    """Serve the Menagerist SVG favicon for interactive documentation."""
    return FileResponse(
        _FAVICON_PATH,
        media_type="image/svg+xml",
        headers={"Cache-Control": _STATIC_CACHE},
    )


@router.get("/docs/logo.svg", include_in_schema=False)
def get_logo() -> FileResponse:
    """Serve the Menagerist SVG logo for interactive documentation."""
    return FileResponse(
        _LOGO_PATH, media_type="image/svg+xml", headers={"Cache-Control": _STATIC_CACHE}
    )


@router.get("/openapi.json", include_in_schema=False)
def get_openapi_schema(request: Request) -> Response:
    """Serve the OpenAPI schema with version-keyed ETag and revalidation caching."""
    etag = f'"{request.app.version}"'
    if request.headers.get("If-None-Match") == etag:
        return Response(
            status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"}
        )
    schema: dict[str, Any] = request.app.openapi()
    return JSONResponse(
        json.loads(json.dumps(schema)),
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )


@router.get("/docs", include_in_schema=False)
def get_swagger_documentation(
    app_info: Annotated[AppInfo, Depends(load_app_info)],
) -> HTMLResponse:
    """Serve the custom Swagger UI documentation page."""
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title=f"{app_info.name} - Swagger UI",
        swagger_favicon_url="/api/docs/favicon.svg",
        oauth2_redirect_url="/api/docs/oauth2-redirect",
    )


@router.get("/docs/oauth2-redirect", include_in_schema=False)
def get_swagger_oauth2_redirect() -> HTMLResponse:
    """Serve the OAuth2 redirect handler for Swagger UI."""
    return get_swagger_ui_oauth2_redirect_html()


@router.get("/redoc", include_in_schema=False)
def get_redoc_documentation(
    app_info: Annotated[AppInfo, Depends(load_app_info)],
) -> HTMLResponse:
    """Serve the custom ReDoc documentation page."""
    return get_redoc_html(
        openapi_url="/api/openapi.json",
        title=f"{app_info.name} - ReDoc",
        redoc_favicon_url="/api/docs/favicon.svg",
    )

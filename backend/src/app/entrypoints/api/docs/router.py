import hashlib
import json
from functools import cache
from html import escape
from pathlib import Path
from string import Template
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_oauth2_redirect_html
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.platform.app_info import AppInfo, load_app_info
from app.platform.config import get_identity_settings

router = APIRouter(route_class=PermissionAwareRoute)

_STATIC_DIR = Path(__file__).parent / "static"
_FAVICON_PATH = _STATIC_DIR / "favicon.svg"
_LOGO_PATH = _STATIC_DIR / "favicon.svg"

_STATIC_CACHE = "public, max-age=86400"

# Exact version plus Subresource Integrity (sha384 of the files served by
# cdn.jsdelivr.net). Update all three together when bumping the version.
_SWAGGER_VERSION = "5.33.0"
_SWAGGER_BASE_URL = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{_SWAGGER_VERSION}"
_SWAGGER_JS_URL = f"{_SWAGGER_BASE_URL}/swagger-ui-bundle.js"
_SWAGGER_CSS_URL = f"{_SWAGGER_BASE_URL}/swagger-ui.css"
_SWAGGER_JS_INTEGRITY = (
    "sha384-YDALVcy8kj8yltLBVi1vBiBAUqdxvus673gM8XKwiy6aDUJFXivF/KCufekjYbVf"
)
_SWAGGER_CSS_INTEGRITY = (
    "sha384-Ov4/wv3j2bmct8cDc5X4ngJZohVPzEmc6uDPH8WeljUxO5vtoykvMEfbu9Vh6RaW"
)

# ReDoc is pinned the same way (sha384 of the file at the URL below).
_REDOC_VERSION = "2.5.4"
_REDOC_JS_URL = (
    f"https://cdn.jsdelivr.net/npm/redoc@{_REDOC_VERSION}/bundles/redoc.standalone.js"
)
_REDOC_JS_INTEGRITY = (
    "sha384-w447zOpYfw/1Tv/5AK9NfHTlQIqE3RVR6KY62jCyy9zNDgO64cMwGGP1Fj0zJVf5"
)

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "swagger.html"
_REDOC_TEMPLATE_PATH = Path(__file__).parent / "templates" / "redoc.html"
_INIT_JS_PATH = _STATIC_DIR / "swagger-init.js"
_INIT_JS_URL = "/api/docs/swagger-init.js"
_REVALIDATE = "no-cache"
_IMMUTABLE = "public, max-age=31536000, immutable"


def render_swagger_page(
    *, title: str, csrf_cookie_name: str, init_js_version: str
) -> str:
    """Fill the Swagger template; every value is HTML-escaped."""
    values = {
        "swagger_css_url": _SWAGGER_CSS_URL,
        "swagger_js_url": _SWAGGER_JS_URL,
        "swagger_css_integrity": _SWAGGER_CSS_INTEGRITY,
        "swagger_js_integrity": _SWAGGER_JS_INTEGRITY,
        "favicon_url": "/api/docs/favicon.svg",
        "title": title,
        "init_js_url": f"{_INIT_JS_URL}?v={init_js_version}",
        "csrf_cookie_name": csrf_cookie_name,
        "openapi_url": "/api/openapi.json",
        "oauth2_redirect_url": "/api/docs/oauth2-redirect",
    }
    template = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.substitute({k: escape(v, quote=True) for k, v in values.items()})


def render_redoc_page(*, title: str) -> str:
    """Fill the ReDoc template; every value is HTML-escaped."""
    values = {
        "favicon_url": "/api/docs/favicon.svg",
        "title": title,
        "openapi_url": "/api/openapi.json",
        "redoc_js_url": _REDOC_JS_URL,
        "redoc_js_integrity": _REDOC_JS_INTEGRITY,
    }
    template = Template(_REDOC_TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.substitute({k: escape(v, quote=True) for k, v in values.items()})


@cache
def _init_js_version() -> str:
    return hashlib.sha256(_INIT_JS_PATH.read_bytes()).hexdigest()[:12]


@cache
def _swagger_body(title: str) -> tuple[bytes, str]:
    """Render once per title: the body and its strong ETag."""
    body = render_swagger_page(
        title=title,
        csrf_cookie_name=get_identity_settings().csrf_cookie_name,
        init_js_version=_init_js_version(),
    ).encode()
    return body, f'"{hashlib.sha256(body).hexdigest()[:32]}"'


def etag_matches(header: str | None, etag: str) -> bool:
    """Weak-compare an If-None-Match header (list, W/ prefix, `*`) with `etag`."""
    if not header:
        return False
    candidates = [part.strip() for part in header.split(",")]
    return "*" in candidates or any(c.removeprefix("W/") == etag for c in candidates)


def _revalidated_html(request: Request, body: bytes, etag: str) -> Response:
    headers = {"ETag": etag, "Cache-Control": _REVALIDATE}
    if etag_matches(request.headers.get("If-None-Match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="text/html; charset=utf-8", headers=headers)


@router.get("/docs/favicon.svg", include_in_schema=False)
@router.get("/favicon.ico", include_in_schema=False)
def get_favicon() -> FileResponse:
    """Serve the Menagerist SVG favicon for interactive documentation."""
    return FileResponse(
        _FAVICON_PATH,
        media_type="image/svg+xml",
        headers={"Cache-Control": _STATIC_CACHE},
    )


@router.get("/docs/swagger-init.js", include_in_schema=False)
def get_swagger_init() -> FileResponse:
    """Serve the Swagger UI setup script (CSRF header and sign-in banner)."""
    return FileResponse(
        _STATIC_DIR / "swagger-init.js",
        media_type="text/javascript",
        headers={"Cache-Control": _IMMUTABLE},
    )


@router.get("/docs/logo.svg", include_in_schema=False)
def get_logo() -> FileResponse:
    """Serve the Menagerist SVG logo for interactive documentation."""
    return FileResponse(
        _LOGO_PATH, media_type="image/svg+xml", headers={"Cache-Control": _STATIC_CACHE}
    )


def _schema_body(app: FastAPI) -> tuple[bytes, str]:
    """Serialise the schema once per schema object, with a strong content ETag."""
    schema: dict[str, Any] = app.openapi()
    cached = getattr(app.state, "openapi_body", None)
    if cached is None or cached[0] is not schema:
        body = json.dumps(schema, separators=(",", ":")).encode()
        cached = (schema, body, f'"{hashlib.sha256(body).hexdigest()[:32]}"')
        app.state.openapi_body = cached
    return cached[1], cached[2]


@router.get("/openapi.json", include_in_schema=False)
def get_openapi_schema(request: Request) -> Response:
    """Serve the OpenAPI schema with a content-hash ETag and revalidation caching."""
    body, etag = _schema_body(request.app)
    headers = {"ETag": etag, "Cache-Control": _REVALIDATE}
    if etag_matches(request.headers.get("If-None-Match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


@router.get("/docs", include_in_schema=False)
def get_swagger_documentation(
    request: Request,
    app_info: Annotated[AppInfo, Depends(load_app_info)],
) -> Response:
    """Serve the custom Swagger UI page, rendered once and revalidated by ETag."""
    body, etag = _swagger_body(f"{app_info.name} - Swagger UI")
    return _revalidated_html(request, body, etag)


@router.get("/docs/oauth2-redirect", include_in_schema=False)
def get_swagger_oauth2_redirect() -> HTMLResponse:
    """Serve the OAuth2 redirect handler for Swagger UI."""
    return get_swagger_ui_oauth2_redirect_html()


@router.get("/redoc", include_in_schema=False)
def get_redoc_documentation(
    app_info: Annotated[AppInfo, Depends(load_app_info)],
) -> HTMLResponse:
    """Serve the custom ReDoc documentation page."""
    return HTMLResponse(render_redoc_page(title=f"{app_info.name} - ReDoc"))

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

_DEFAULT_CSP = "; ".join(
    [
        "default-src 'none'",
        "img-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
    ]
)

_DOCS_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        (
            "style-src 'self' 'unsafe-inline' "
            + "https://cdn.jsdelivr.net https://fonts.googleapis.com"
        ),
        "img-src 'self' data:",
        "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net",
        "connect-src 'self' https://cdn.jsdelivr.net",
        "worker-src 'self' blob:",
        "frame-ancestors 'none'",
        "base-uri 'self'",
    ]
)

_DOCS_PATHS: frozenset[str] = frozenset(
    {
        "/api/docs",
        "/api/redoc",
    }
)

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "no-referrer",
}

_DEFAULT_CACHE_CONTROL = "no-store"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Stamp every response with baseline security headers and default caching."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Add baseline security headers and a default Cache-Control."""
        response = await call_next(request)
        path = request.url.path.rstrip("/")
        is_docs = path in _DOCS_PATHS or path.startswith(
            ("/api/docs", "/docs", "/api/redoc", "/redoc")
        )
        csp = _DOCS_CSP if is_docs else _DEFAULT_CSP
        response.headers.setdefault("Content-Security-Policy", csp)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        response.headers.setdefault("Cache-Control", _DEFAULT_CACHE_CONTROL)
        return response

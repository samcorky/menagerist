"""Serve the built SvelteKit SPA (adapter-static) from the API process.

Replaces the nginx frontend container. Mounted at ``/`` *after* the API routers,
so anything under ``/api`` is matched by the API first; this only sees the rest.

Behaviour mirrors ``frontend/nginx.conf``:

* ``_app/immutable/*`` (content-hashed)       -> cached for a year, immutable
* other real files (icons, fonts, ...)        -> cached for an hour
* missing files that look like assets         -> 404 (not the HTML shell, which
                                                  would turn a stale hashed asset
                                                  into a confusing JS parse error)
* dotfiles (except ``.well-known``)           -> 404
* unknown ``/api/*`` paths                    -> 404 (never the shell)
* ``/favicon.ico``                            -> 301 ``/favicon.svg``
* any other path (client-side routes)         -> the SPA shell (``200.html``),
                                                  never cached, with the SPA's CSP

Security headers on the shell are set explicitly. ``SecurityHeadersMiddleware``
uses ``setdefault``, so it fills in the API-oriented defaults (CSP ``default-src
'none'``) only where a response hasn't already chosen its own.
"""

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse, Response
from starlette.staticfiles import StaticFiles

if TYPE_CHECKING:
    from starlette.types import Scope

_SHELL = "200.html"
_IMMUTABLE_PREFIX = "_app/immutable/"

_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
_ASSET_CACHE = "public, max-age=3600"
_NO_CACHE = "no-store, no-cache, must-revalidate"

_SHELL_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self' data: https://fonts.gstatic.com",
        "img-src 'self' blob: data:",
        "connect-src 'self'",
    ]
)
_SHELL_HEADERS: dict[str, str] = {
    "Cache-Control": _NO_CACHE,
    "Content-Security-Policy": _SHELL_CSP,
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def _is_hidden(path: str) -> bool:
    return any(
        part.startswith(".") and part != ".well-known"
        for part in PurePosixPath(path).parts
    )


def _looks_like_asset(path: str) -> bool:
    return "." in PurePosixPath(path).name


class SpaStaticFiles(StaticFiles):
    """StaticFiles with SPA-shell fallback and per-path caching."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve `path`, falling back to the SPA shell for client-side routes."""
        # StaticFiles.get_path() returns OS-specific separators; normalize to
        # "/" since every comparison below (PurePosixPath, _IMMUTABLE_PREFIX)
        # assumes POSIX-style paths regardless of platform.
        path = path.replace("\\", "/")
        if path == "favicon.ico":
            return RedirectResponse("/favicon.svg", status_code=301)
        if _is_hidden(path) or path.startswith("api/") or path == "api":
            raise HTTPException(status_code=404)

        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or _looks_like_asset(path):
                raise
            return self._shell(await super().get_response(_SHELL, scope))

        if path == _SHELL:
            return self._shell(response)

        response.headers["Cache-Control"] = (
            _IMMUTABLE_CACHE if path.startswith(_IMMUTABLE_PREFIX) else _ASSET_CACHE
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @staticmethod
    def _shell(response: Response) -> Response:
        for name, value in _SHELL_HEADERS.items():
            response.headers[name] = value
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

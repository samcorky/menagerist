import re
import time
import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from app.platform.config import get_logging_settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import Scope

_REQUEST_ID_HEADER = "Request-Id"
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_LOGGED_PREFIX = "/api/"
# Probe polling is noise; non-API paths are the SPA's static files.
_QUIET_PREFIXES = ("/api/health",)

access_logger = structlog.get_logger("app.access")


def _loggable_path(scope: Scope) -> str:
    """Return the still percent-encoded path, with any control character escaped.

    The decoded `scope["path"]` can hold newlines or ANSI escapes sent as `%0a`
    or `%1b`; logging it would let a client forge log lines.
    """
    raw = scope.get("raw_path")
    path = (
        raw.decode("ascii", "replace").split("?", 1)[0]
        if isinstance(raw, bytes)
        else scope["path"]
    )
    return _CONTROL_CHARS.sub(lambda m: f"\\x{ord(m.group()):02x}", path)


def _is_logged(path: str) -> bool:
    return path.startswith(_LOGGED_PREFIX) and not path.startswith(_QUIET_PREFIXES)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request-scoped ID into structlog context, echo it back and log it.

    One access-style line is written per request after the response. It never
    includes the query string or any header.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Bind a request ID for the request lifecycle and echo it in the response."""
        supplied = request.headers.get(_REQUEST_ID_HEADER, "")
        request_id = (
            supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else str(uuid.uuid7())
        )
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            started = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                self._log(request, 500, started)
                raise
            response.headers[_REQUEST_ID_HEADER] = request_id
            self._log(request, response.status_code, started)
            return response

    @staticmethod
    def _log(request: Request, status: int, started: float) -> None:
        path = _loggable_path(request.scope)
        if not get_logging_settings().access or not _is_logged(path):
            return
        method = request.method
        fields: dict[str, object] = {
            "addr": request.client.host if request.client else "-",
            "method": method,
            "path": path,
            "protocol": f"HTTP/{request.scope.get('http_version', '1.1')}",
            "status": status,
            "dt_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        for key in ("user_id", "session_id", "token_id"):
            if (value := getattr(request.state, key, None)) is not None:
                fields[key] = value
        log = access_logger.warning if status >= 500 else access_logger.info
        log(f"{method} {path}", **fields)

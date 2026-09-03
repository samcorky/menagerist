import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

_REQUEST_ID_HEADER = "Request-Id"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request-scoped ID into structlog context and echo it back."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Bind a request ID for the request lifecycle and echo it in the response."""
        request_id = request.headers.get(_REQUEST_ID_HEADER) or str(uuid.uuid7())
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            response = await call_next(request)
            response.headers[_REQUEST_ID_HEADER] = request_id
            return response

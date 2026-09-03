from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from app.platform.app_info import load_app_info

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp


class VersionHeaderMiddleware(BaseHTTPMiddleware):
    """Stamp every response with an App-Version header."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._version = load_app_info().version

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Add App-Version to every response."""
        response = await call_next(request)
        response.headers["App-Version"] = self._version
        return response

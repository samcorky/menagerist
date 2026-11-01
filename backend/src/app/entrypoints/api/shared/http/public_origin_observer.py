from typing import TYPE_CHECKING

from starlette.datastructures import Headers

from app.entrypoints.api.shared.http.origin import claimed_origin, origin_of
from app.platform import proxy_signals
from app.platform.proxy_signals import ProxySignal

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

# The container's own health check calls localhost, so it never reflects how people
# reach the app.
_IGNORED_PREFIX = "/api/health"


class PublicOriginObserver:
    """Pure ASGI middleware that notes requests not made at the public origin.

    Sits inside Granian's proxy-header wrapper, so the scheme and host are those a
    trusted proxy forwarded. It only records a time per request; behaviour is
    unchanged.
    """

    def __init__(self, app: ASGIApp, *, public_origin: str) -> None:
        self._app = app
        self._public = public_origin
        self._public_https = public_origin.startswith("https://")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Compare the request's origin with the public one, then pass it on."""
        if scope["type"] == "http" and not scope["path"].startswith(_IGNORED_PREFIX):
            self._note(scope)
        await self._app(scope, receive, send)

    def _note(self, scope: Scope) -> None:
        host = Headers(scope=scope).get("host")
        if not host:
            return
        seen = claimed_origin(origin_of(scope["scheme"], host))
        if seen == self._public:
            return
        if self._public_https and scope["scheme"] == "http":
            proxy_signals.record(ProxySignal.INSECURE_ORIGIN)
        else:
            proxy_signals.record(ProxySignal.PUBLIC_ORIGIN_MISMATCH)

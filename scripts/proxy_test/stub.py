"""A stand-in upstream for the reverse proxy test: the real upload guard, no database.

Mounted into the Menagerist image by `compose.proxy.yaml` and served by Granian
exactly as `menagerist serve` serves the app. Every request that gets past the
guard is answered 401 without its body being read, the way the app answers an
unauthenticated upload, so both ways of replying early are covered: the guard's
413 and the app's own 401.
"""

from typing import TYPE_CHECKING

from app.entrypoints.api.shared.http.upload_limit_middleware import (
    UploadLimitMiddleware,
)

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send


async def _unauthenticated(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        return
    await send({"type": "http.response.start", "status": 401, "headers": []})
    await send({"type": "http.response.body", "body": b""})


app = UploadLimitMiddleware(_unauthenticated)

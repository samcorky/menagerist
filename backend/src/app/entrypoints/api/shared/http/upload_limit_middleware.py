import json
from typing import TYPE_CHECKING

from starlette.datastructures import Headers

from app.platform.config import get_backup_settings, get_media_settings

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Multipart boundaries and the small form fields come on top of the file.
_OVERHEAD_ALLOWANCE = 64 * 1024

_UPLOAD_PATHS = frozenset({"/api/v1/media", "/api/v1/media/attached"})
_BACKUP_PATHS = frozenset(
    {
        "/api/v1/backup/upload",
        "/api/v1/backup/first-run-restore",
        "/api/v1/me/import",
    }
)

PAYLOAD_TOO_LARGE_RESPONSE: dict[int | str, dict[str, object]] = {
    413: {
        "description": "The request body is larger than the upload limit.",
        "content": {
            "application/problem+json": {
                "example": {
                    "type": "about:blank",
                    "title": "Payload Too Large",
                    "status": 413,
                    "detail": "The upload is larger than this server allows.",
                    "instance": "string",
                }
            }
        },
    }
}


def _is_upload(scope: Scope) -> bool:
    return (
        scope["type"] == "http"
        and scope["method"] == "POST"
        and scope["path"] in _UPLOAD_PATHS | _BACKUP_PATHS
    )


async def _refuse(scope: Scope, send: Send) -> None:
    body = json.dumps(
        {
            "type": "about:blank",
            "title": "Payload Too Large",
            "status": 413,
            "detail": "The upload is larger than this server allows.",
            "instance": scope["path"],
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/problem+json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class _BodyCounter:
    """Counts a request body as it is read and swaps in a 413 once over `limit`.

    FastAPI turns any error raised while reading the form into a 400, so after
    the cut-off the app is told the client disconnected and whatever it then
    sends is replaced by one 413.
    """

    def __init__(self, scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        self._scope = scope
        self._receive = receive
        self._send = send
        self._limit = limit
        self._received = 0
        self._exceeded = False
        self._refused = False

    async def receive(self) -> Message:
        if self._exceeded:
            return {"type": "http.disconnect"}
        message = await self._receive()
        if message["type"] == "http.request":
            self._received += len(message.get("body", b""))
            self._exceeded = self._received > self._limit
            if self._exceeded:
                return {"type": "http.disconnect"}
        return message

    async def send(self, message: Message) -> None:
        if not self._exceeded:
            await self._send(message)
        else:
            await self.finish()

    async def finish(self) -> None:
        """Send the 413 once if the body went over the limit."""
        if self._exceeded and not self._refused:
            self._refused = True
            await _refuse(self._scope, self._send)


class UploadLimitMiddleware:
    """Refuse an oversize upload before the multipart body is parsed.

    FastAPI reads and spools the whole form before it runs any dependency, so
    without this an anonymous client could fill the disk with a body that is
    only rejected, as unauthenticated, afterwards. A declared `Content-Length`
    over the limit is refused without reading; a body with no length (chunked)
    is counted as it arrives and aborted once it passes the limit.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass other requests on untouched; guard the upload routes."""
        if not _is_upload(scope):
            await self._app(scope, receive, send)
            return

        limit = (
            get_backup_settings().max_upload_size
            if scope["path"] in _BACKUP_PATHS
            else get_media_settings().max_upload_size + _OVERHEAD_ALLOWANCE
        )
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _refuse(scope, send)
            return

        counter = _BodyCounter(scope, receive, send, limit)
        await self._app(scope, counter.receive, counter.send)
        await counter.finish()

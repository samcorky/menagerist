"""Oversize uploads are refused before the multipart body is parsed."""

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.http import upload_limit_middleware
from app.entrypoints.api.shared.http.upload_limit_middleware import (
    UploadLimitMiddleware,
)
from app.platform.config.backup import BackupSettings
from app.platform.config.media import MediaSettings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from starlette.types import ASGIApp, Message, Receive, Scope, Send

LIMIT = 1000
ALLOWANCE = upload_limit_middleware._OVERHEAD_ALLOWANCE


@pytest.mark.parametrize(
    "path",
    ["/api/v1/backup/upload", "/api/v1/backup/first-run-restore", "/api/v1/me/import"],
)
async def test_archive_uploads_use_backup_limit(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Archive limits apply before authentication and have no multipart allowance."""
    monkeypatch.setattr(
        upload_limit_middleware,
        "get_backup_settings",
        lambda: BackupSettings(max_upload_size=20),
    )
    sent, reads = await _call("POST", path, [(b"content-length", b"21")], [b"x"])
    assert sent[0]["status"] == 413
    assert reads == 1
    sent, _ = await _call("POST", path, [], [b"x" * 11, b"y" * 11])
    assert sent[0]["status"] == 413
    sent, _ = await _call("POST", path, [], [b"x" * 20])
    assert sent[0]["status"] == 204


@pytest.fixture(autouse=True)
def _small_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        upload_limit_middleware,
        "get_media_settings",
        lambda: MediaSettings(max_upload_size=LIMIT),
    )


async def _call(
    method: str, path: str, headers: list[tuple[bytes, bytes]], bodies: list[bytes]
) -> tuple[list[Message], int]:
    """Run the middleware over a stub app; return what it sent and chunks read."""
    reads = 0
    sent: list[Message] = []
    remaining = list(bodies)
    downstream_ran = False

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal downstream_ran
        downstream_ran = True
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive() -> Message:
        nonlocal reads
        reads += 1
        body = remaining.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(remaining)}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
    }
    await UploadLimitMiddleware(app)(scope, receive, send)
    sent.append({"type": "marker", "downstream": downstream_ran})
    return sent, reads


async def test_declared_length_over_the_limit_is_refused_and_drained() -> None:
    """The app never runs; the body is read only to be discarded."""
    headers = [(b"content-length", str(LIMIT + ALLOWANCE + 1).encode())]

    sent, reads = await _call("POST", "/api/v1/media", headers, [b"x"])

    assert reads == 1
    assert sent[0]["status"] == 413
    assert (b"content-type", b"application/problem+json") in sent[0]["headers"]
    assert json.loads(sent[1]["body"])["status"] == 413
    assert sent[-1]["downstream"] is False


async def test_chunked_body_over_the_limit_is_aborted_part_way() -> None:
    """With no length the app is cut off past the limit; the rest is drained."""
    chunk = b"x" * (ALLOWANCE)
    seen: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        while (message := await receive())["type"] == "http.request":
            seen.append("chunk")
        seen.append(message["type"])

    reads, sent = await _run_with_stub_app(app, [chunk, chunk, chunk, chunk])

    assert sent[0]["status"] == 413
    assert seen == ["chunk", "http.disconnect"]
    assert reads == 4


async def _run_with_stub_app(
    app: ASGIApp, bodies: list[bytes]
) -> tuple[int, list[Message]]:
    reads = 0
    sent: list[Message] = []
    remaining = list(bodies)

    async def receive() -> Message:
        nonlocal reads
        reads += 1
        body = remaining.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(remaining)}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/media/attached",
        "headers": [],
    }
    await UploadLimitMiddleware(app)(scope, receive, send)
    return reads, sent


async def test_reply_goes_out_before_the_rest_of_the_body_is_read() -> None:
    """The 413 is sent first, so the client can read it while still writing."""
    log: list[str] = []
    remaining = [b"x" * (LIMIT + ALLOWANCE + 1), b"y", b"z"]

    async def receive() -> Message:
        log.append("read")
        body = remaining.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(remaining)}

    async def send(message: Message) -> None:
        log.append(message["type"])

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/media",
        "headers": [],
    }
    await UploadLimitMiddleware(app)(scope, receive, send)

    assert log == [
        "read",
        "http.response.start",
        "http.response.body",
        "read",
        "read",
    ]


async def test_an_early_reply_to_an_unread_body_drains_it() -> None:
    """A 401 sent without reading the body is followed by reading the rest."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    reads, sent = await _run_with_stub_app(app, [b"a", b"b", b"c"])

    assert sent[0]["status"] == 401
    assert reads == 3


async def test_a_fully_read_body_is_not_read_again() -> None:
    """Nothing is left to drain once the app has taken the last chunk."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        while (await receive()).get("more_body"):
            pass
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    reads, _ = await _run_with_stub_app(app, [b"a", b"b"])

    assert reads == 2


async def test_drain_stops_at_the_byte_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """A body that keeps coming is abandoned after the bound."""
    monkeypatch.setattr(upload_limit_middleware, "_DRAIN_BYTES", 250)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        return None

    reads, _ = await _run_with_stub_app(app, [b"x" * 100] * 10)

    assert reads == 3


async def test_drain_stops_at_the_time_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """A client that trickles or stalls cannot hold the request open."""
    monkeypatch.setattr(upload_limit_middleware, "_DRAIN_SECONDS", 0.05)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        return None

    async def receive() -> Message:
        await asyncio.sleep(10)
        raise AssertionError

    async def send(message: Message) -> None:
        return None

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/media",
        "headers": [(b"content-length", str(LIMIT + ALLOWANCE + 1).encode())],
    }
    await UploadLimitMiddleware(app)(scope, receive, send)


async def test_drain_ends_on_a_disconnect() -> None:
    """A client that goes away ends the drain."""
    calls = 0

    async def receive() -> Message:
        nonlocal calls
        calls += 1
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        return None

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        return None

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/media",
        "headers": [],
    }
    await UploadLimitMiddleware(app)(scope, receive, send)

    assert calls == 1


async def test_body_within_the_limit_passes_through() -> None:
    """A small chunked body reaches the app."""
    sent, _ = await _call("POST", "/api/v1/media", [], [b"x" * 10, b"y" * 10])

    assert sent[0]["status"] == 204


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/api/v1/node"), ("PATCH", "/api/v1/media"), ("POST", "/api/v1/media/x")],
)
async def test_other_requests_are_not_limited(method: str, path: str) -> None:
    """Only the two upload routes are guarded."""
    big = [(b"content-length", str(LIMIT * 100).encode())]

    sent, _ = await _call(method, path, big, [b"x"])

    assert sent[0]["status"] == 204


async def test_non_http_scopes_pass_through() -> None:
    """Lifespan and websocket scopes are untouched."""
    seen: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    await UploadLimitMiddleware(app)({"type": "lifespan"}, _no_receive, _no_send)

    assert seen == ["lifespan"]


async def test_the_apps_own_answer_is_replaced_by_the_413() -> None:
    """Whatever the app sends after the cut-off (FastAPI sends a 400) is dropped."""
    sent: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send({"type": "http.response.body", "body": b"bad"})

    async def receive() -> Message:
        return {"type": "http.request", "body": b"x" * (LIMIT + ALLOWANCE + 1)}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/media",
        "headers": [],
    }
    await UploadLimitMiddleware(app)(scope, receive, send)

    assert [m["status"] for m in sent if m["type"] == "http.response.start"] == [413]


async def test_a_413_is_sent_even_if_the_app_stays_silent() -> None:
    """An app that returns without answering after the cut-off still gets a 413."""
    sent: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()

    async def receive() -> Message:
        return {"type": "http.request", "body": b"x" * (LIMIT + ALLOWANCE + 1)}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/media",
        "headers": [],
    }
    await UploadLimitMiddleware(app)(scope, receive, send)

    assert sent[0]["status"] == 413


async def test_later_reads_after_the_cut_off_report_a_disconnect() -> None:
    """The app sees a disconnect, never more of the oversize body."""
    seen: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append((await receive())["type"])
        seen.append((await receive())["type"])

    async def receive() -> Message:
        return {"type": "http.request", "body": b"x" * (LIMIT + ALLOWANCE + 1)}

    async def send(message: Message) -> None:
        return None

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/media",
        "headers": [],
    }
    await UploadLimitMiddleware(app)(scope, receive, send)

    assert seen == ["http.disconnect", "http.disconnect"]


async def _no_receive() -> Message:
    raise AssertionError


async def _no_send(message: Message) -> None:
    raise AssertionError


def _chunks(total: int) -> Iterator[bytes]:
    for _ in range(total // 100):
        yield b"x" * 100


def test_unauthenticated_oversize_is_refused_before_auth() -> None:
    """No session and a too-large body: 413, not 401."""
    app = create_app()
    client = TestClient(app)
    client.cookies.clear()

    response = client.post(
        "/api/v1/media",
        files={"file": ("big.bin", b"x" * (LIMIT + ALLOWANCE + 10), "image/png")},
    )

    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_chunked_oversize_through_the_app_is_413() -> None:
    """A streamed body with no length is cut off through the whole stack."""
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/media/attached",
        content=_chunks(LIMIT + ALLOWANCE + 1000),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 413

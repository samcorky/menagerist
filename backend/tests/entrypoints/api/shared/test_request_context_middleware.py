from typing import TYPE_CHECKING

import structlog
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.request_context_middleware import (
    RequestContextMiddleware,
)

if TYPE_CHECKING:
    from starlette.requests import Request


async def _echo_context(_request: Request) -> JSONResponse:
    """Test-only endpoint that reports what's bound in structlog's contextvars."""
    return JSONResponse(dict(structlog.contextvars.get_contextvars()))


def _context_probe_app() -> Starlette:
    app = Starlette(routes=[Route("/context", _echo_context)])
    app.add_middleware(RequestContextMiddleware)
    return app


def test_response_carries_generated_request_id() -> None:
    """A request with no `Request-Id` gets one minted and echoed back."""
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["request-id"]


def test_inbound_request_id_is_reused() -> None:
    """A caller-supplied `Request-Id` is echoed back unchanged, not replaced."""
    client = TestClient(create_app())

    response = client.get("/api/health", headers={"Request-Id": "abc-123"})

    assert response.headers["request-id"] == "abc-123"


def test_each_request_gets_a_distinct_generated_id() -> None:
    """Two requests with no inbound header mint two different IDs."""
    client = TestClient(create_app())

    first = client.get("/api/health")
    second = client.get("/api/health")

    assert first.headers["request-id"] != second.headers["request-id"]


def test_request_id_is_bound_into_structlog_context_during_the_request() -> None:
    """Application code can read `request_id` off structlog's contextvars."""
    client = TestClient(_context_probe_app())

    response = client.get("/context", headers={"Request-Id": "probe-id"})

    assert response.json()["request_id"] == "probe-id"


def test_contextvars_are_cleared_between_requests() -> None:
    """One request's bound `request_id` must not leak into the next request."""
    client = TestClient(_context_probe_app())

    client.get("/context", headers={"Request-Id": "first-request"})
    second = client.get("/context")

    assert second.json()["request_id"] != "first-request"


def test_non_http_scope_passes_through_untouched() -> None:
    """Non-HTTP ASGI scopes (e.g. lifespan) bypass request-id binding entirely."""
    with TestClient(_context_probe_app()) as client:
        # Entering the context manager drives the lifespan protocol; if the
        # middleware mishandled a non-"http" scope type, startup would fail here.
        response = client.get("/context")
        assert response.status_code == 200

"""Problem mapping for authentication-related domain errors."""

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.entrypoints.api.shared.problem_response import register_exception_handlers
from app.shared_kernel.errors import TooManyRequestsError, UnauthenticatedError


def _client(error: Exception) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise error

    return TestClient(app, raise_server_exceptions=False)


def test_unauthenticated_maps_to_401() -> None:
    """UnauthenticatedError answers 401 with the default problem type."""
    response = _client(UnauthenticatedError("Nope")).get("/boom")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "about:blank"
    assert response.json()["title"] == "UnauthenticatedError"


def test_too_many_requests_maps_to_429_with_retry_after() -> None:
    """TooManyRequestsError answers 429 and sets Retry-After."""
    response = _client(TooManyRequestsError("Slow down", retry_after=90)).get("/boom")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "90"


def test_too_many_requests_without_retry_after_omits_header() -> None:
    """No Retry-After header is sent when the wait is unknown."""
    response = _client(TooManyRequestsError("Slow down")).get("/boom")

    assert response.status_code == 429
    assert "retry-after" not in response.headers


def test_problem_type_is_used_in_the_body() -> None:
    """A subclass can name its own problem type."""
    response = _client(UnauthenticatedError("x")).get("/boom")
    assert response.json()["type"] == "about:blank"

    class _SetupError(UnauthenticatedError):
        problem_type = "setup_required"

    assert _client(_SetupError("x")).get("/boom").json()["type"] == "setup_required"

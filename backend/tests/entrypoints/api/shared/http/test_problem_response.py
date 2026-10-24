"""Problem mapping for authentication-related domain errors."""

from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from app.entrypoints.api.shared.http.problem_response import register_exception_handlers
from app.shared_kernel.errors import (
    NotFoundError,
    TooManyRequestsError,
    UnauthenticatedError,
)


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


def test_unhandled_error_text_is_logged_not_returned() -> None:
    """A non-domain exception gives a fixed 500; its text stays in the log."""
    secret = "postgresql://user:hunter2@db/menagerist"
    with capture_logs() as logs:
        response = _client(RuntimeError(secret)).get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["title"] == "Internal Server Error"
    assert body["detail"] == "An unexpected error occurred."
    assert secret not in response.text
    assert "RuntimeError" not in response.text
    (entry,) = [e for e in logs if e["event"] == "unhandled exception"]
    assert str(entry["exc_info"]) == secret


class _Login(BaseModel, extra="forbid"):
    username: str
    password: str = Field(max_length=10)


def test_validation_error_never_echoes_what_was_submitted() -> None:
    """422 keeps type, loc and msg but drops `input` and `ctx`."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/login")
    async def login(body: _Login) -> None:
        return None

    submitted = "a-password-long-enough-to-fail".replace("-", " ")
    response = TestClient(app).post(
        "/login",
        json={"username": "sam", "password": submitted, "x": "leak"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == 422
    errors = body["detail"]
    assert {e["type"] for e in errors} == {"string_too_long", "extra_forbidden"}
    assert all(set(e) == {"type", "loc", "msg"} for e in errors)
    assert ["body", "password"] in [e["loc"] for e in errors]
    assert submitted not in response.text
    assert "leak" not in response.text


def test_malformed_json_does_not_echo_the_body() -> None:
    """A syntax error answers 422 without the raw body."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/login")
    async def login(body: _Login) -> None:
        return None

    response = TestClient(app).post(
        "/login",
        content=b'{"password": "hunter2"',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert "hunter2" not in response.text


def _routed_client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/api/v1/thing")
    async def thing() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/api/v1/missing")
    async def missing() -> None:
        raise NotFoundError("Thing 1 was not found.")

    @app.get("/page")
    async def page() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app)


def test_unknown_api_path_is_a_problem_response() -> None:
    """A path nothing serves under /api answers like any other 404."""
    response = _routed_client().get("/api/v1/items")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "NotFoundError",
        "status": 404,
        "detail": "No such API endpoint.",
        "instance": "http://testserver/api/v1/items",
    }


def test_wrong_method_is_a_problem_response_with_allow() -> None:
    """A known path with the wrong verb is a 405 problem that keeps Allow."""
    response = _routed_client().post("/api/v1/thing")

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"
    assert "GET" in response.headers["allow"]
    assert response.json() == {
        "type": "about:blank",
        "title": "MethodNotAllowedError",
        "status": 405,
        "detail": "This endpoint does not accept POST.",
        "instance": "http://testserver/api/v1/thing",
    }


def test_a_routes_own_404_is_unchanged() -> None:
    """Domain 404s keep their own detail."""
    response = _routed_client().get("/api/v1/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Thing 1 was not found."


def test_non_api_paths_keep_the_framework_default() -> None:
    """Only /api is reshaped; elsewhere the default response stands."""
    client = _routed_client()

    not_found = client.get("/elsewhere")
    wrong_method = client.post("/page")

    assert not_found.status_code == 404
    assert not_found.json() == {"detail": "Not Found"}
    assert wrong_method.status_code == 405
    assert wrong_method.json() == {"detail": "Method Not Allowed"}

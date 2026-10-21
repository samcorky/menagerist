"""What a listed cross-origin page may ask of the API, and what it may read back."""

import pytest
from fastapi.routing import APIRoute
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.http.cors import (
    CORS_METHODS,
    CORS_REQUEST_HEADERS,
    CORS_RESPONSE_HEADERS,
)
from app.platform.config.api import ApiSettings

ALLOWED = "https://app.example"
STATUS = "/api/v1/auth/status"
LIVENESS = "/api/health"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A client for an app that lists one cross-origin site."""
    monkeypatch.setattr(
        "app.entrypoints.api.get_api_settings",
        lambda: ApiSettings(cors_origins=[ALLOWED]),
    )
    return TestClient(create_app())


def _preflight(
    client: TestClient,
    *,
    origin: str = ALLOWED,
    method: str = "PATCH",
    headers: str = "",
) -> tuple[int, dict[str, str]]:
    request_headers = {
        "Origin": origin,
        "Access-Control-Request-Method": method,
    }
    if headers:
        request_headers["Access-Control-Request-Headers"] = headers
    response = client.options(STATUS, headers=request_headers)
    return response.status_code, dict(response.headers)


def test_the_lists_hold_no_wildcard() -> None:
    """Nothing is waved through by name."""
    for values in (CORS_METHODS, CORS_REQUEST_HEADERS, CORS_RESPONSE_HEADERS):
        assert "*" not in values


def test_authorization_is_not_yet_allowed() -> None:
    """The header joins the list in the change that adds API tokens."""
    assert "Authorization" not in CORS_REQUEST_HEADERS


def test_an_allowed_preflight_gets_the_allow_headers_and_max_age(
    client: TestClient,
) -> None:
    """A listed origin, method and headers is answered, and cached for ten minutes."""
    status, headers = _preflight(client, headers="content-type, if-match")

    assert status == 200
    assert headers["access-control-allow-origin"] == ALLOWED
    assert headers["access-control-max-age"] == "600"
    assert "PATCH" in headers["access-control-allow-methods"]
    assert "access-control-allow-credentials" not in headers


@pytest.mark.parametrize("method", CORS_METHODS)
def test_every_listed_method_is_allowed(client: TestClient, method: str) -> None:
    """The five methods the API serves can all be asked for."""
    status, _ = _preflight(client, method=method)

    assert status == 200


@pytest.mark.parametrize("method", ["PROPFIND", "TRACE", "CONNECT"])
def test_an_unlisted_method_is_refused(client: TestClient, method: str) -> None:
    """A method the API does not serve gets 400 and no allowance."""
    status, _ = _preflight(client, method=method)

    assert status == 400


@pytest.mark.parametrize("header", ["authorization", "x-csrf-token", "x-anything"])
def test_an_unlisted_header_is_refused(client: TestClient, header: str) -> None:
    """A preflight asking for another header is refused, not echoed back."""
    status, _ = _preflight(client, headers=header)

    assert status == 400


def test_an_unlisted_origin_is_refused(client: TestClient) -> None:
    """Another site gets no preflight approval."""
    status, headers = _preflight(client, origin="https://evil.example")

    assert status == 400
    assert "access-control-allow-origin" not in headers


def test_a_listed_origin_can_read_the_headers_the_api_relies_on(
    client: TestClient,
) -> None:
    """`ETag`, `Retry-After` and the paging headers are exposed cross-origin."""
    response = client.get(LIVENESS, headers={"Origin": ALLOWED})

    assert response.headers["access-control-allow-origin"] == ALLOWED
    exposed = response.headers["access-control-expose-headers"].lower()
    for name in CORS_RESPONSE_HEADERS:
        assert name.lower() in exposed
    assert "etag" in exposed
    assert "retry-after" in exposed


def test_a_same_origin_request_is_unaffected(client: TestClient) -> None:
    """No `Origin` means no CORS headers, and the request is served as before."""
    client.headers.pop("Origin", None)

    response = client.get(LIVENESS)

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


# Headers any browser may send or read without being listed.
_SAFELISTED_REQUEST = {"accept", "accept-language", "content-language", "content-type"}
_SAFELISTED_RESPONSE = {
    "cache-control",
    "content-language",
    "content-length",
    "content-type",
    "expires",
    "last-modified",
    "pragma",
}


# Acted on by the browser itself; page script never reads it.
_BROWSER_ONLY_RESPONSE = {"clear-site-data"}


def test_every_route_uses_a_listed_method() -> None:
    """A new route method must join `CORS_METHODS`, or its preflight is refused."""
    used = {
        method
        for route in create_app().routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }

    assert used <= set(CORS_METHODS) | {"HEAD", "OPTIONS"}, used - set(CORS_METHODS)


def _operations() -> list[dict[str, object]]:
    schema = create_app().openapi()
    return [op for path in schema["paths"].values() for op in path.values()]


def test_every_declared_request_header_is_listed() -> None:
    """A header parameter on any operation must be in `CORS_REQUEST_HEADERS`."""
    listed = {name.lower() for name in CORS_REQUEST_HEADERS} | _SAFELISTED_REQUEST
    declared = {
        parameter["name"].lower()
        for operation in _operations()
        for parameter in operation.get("parameters", [])  # type: ignore[attr-defined]
        if parameter["in"] == "header"
    }

    assert declared <= listed, declared - listed


def test_every_declared_response_header_is_exposed() -> None:
    """A response header in the schema must be in `CORS_RESPONSE_HEADERS`."""
    exposed = (
        {name.lower() for name in CORS_RESPONSE_HEADERS}
        | _SAFELISTED_RESPONSE
        | _BROWSER_ONLY_RESPONSE
    )
    declared = {
        name.lower()
        for operation in _operations()
        for response in operation.get("responses", {}).values()  # type: ignore[attr-defined]
        for name in response.get("headers", {})
    }

    assert declared <= exposed, declared - exposed

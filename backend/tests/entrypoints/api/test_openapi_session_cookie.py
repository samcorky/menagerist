"""The `Set-Cookie` docs match the routes that really set or clear the cookie."""

from typing import Any

import pytest

from app.entrypoints.api import create_app

_METHODS = ("get", "put", "post", "delete", "patch")
DOCUMENTED = {
    ("post", "/api/v1/auth/setup", "201"),
    ("post", "/api/v1/auth/login", "200"),
    ("post", "/api/v1/auth/password", "200"),
    ("post", "/api/v1/auth/logout", "204"),
}


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    """The generated OpenAPI document."""
    return create_app().openapi()


def _with_set_cookie(schema: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (method, path, status)
        for path, item in schema["paths"].items()
        for method, operation in item.items()
        if method in _METHODS
        for status, response in operation["responses"].items()
        if "Set-Cookie" in response.get("headers", {})
    }


def test_only_the_session_routes_document_set_cookie(schema: dict[str, Any]) -> None:
    """No other route documents the cookie."""
    assert _with_set_cookie(schema) == DOCUMENTED


def test_the_cookie_is_described_and_logout_says_it_is_cleared(
    schema: dict[str, Any],
) -> None:
    """The header text names the cookie's real attributes."""
    paths = schema["paths"]
    login = paths["/api/v1/auth/login"]["post"]["responses"]["200"]
    logout = paths["/api/v1/auth/logout"]["post"]["responses"]["204"]
    for header in (login["headers"]["Set-Cookie"], logout["headers"]["Set-Cookie"]):
        text = header["description"]
        assert "HttpOnly" in text
        assert "SameSite=Strict" in text
        assert "Secure" in text
        assert "__Host-Http-" in text
    assert "opaque" in login["headers"]["Set-Cookie"]["description"]
    assert "Max-Age=0" in logout["headers"]["Set-Cookie"]["description"]
    assert "Clear-Site-Data" in logout["headers"]
    assert "content" in login

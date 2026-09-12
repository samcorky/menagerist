import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.security_headers import SecurityHeadersMiddleware


def _endpoint(request: object) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _custom_csp_endpoint(request: object) -> Response:
    return PlainTextResponse(
        "ok", headers={"Content-Security-Policy": "default-src 'self'"}
    )


def test_security_headers_middleware_attaches_headers() -> None:
    """SecurityHeadersMiddleware injects nosniff, frame-deny, csp headers."""
    app = Starlette(routes=[Route("/", _endpoint)])
    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in resp.headers["Content-Security-Policy"]


@pytest.mark.parametrize(
    "path",
    ["/api/docs", "/api/redoc", "/docs", "/redoc", "/api/docs/", "/api/redoc/"],
)
def test_security_headers_middleware_allows_docs_csp(path: str) -> None:
    """Documentation endpoints receive a relaxed CSP allowing CDN assets and scripts."""
    app = Starlette(
        routes=[
            Route("/api/docs", _endpoint),
            Route("/api/redoc", _endpoint),
            Route("/docs", _endpoint),
            Route("/redoc", _endpoint),
            Route("/api/docs/", _endpoint),
            Route("/api/redoc/", _endpoint),
        ]
    )
    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)

    resp = client.get(path)
    assert resp.status_code == 200
    csp = resp.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in csp
    assert "'unsafe-inline'" in csp
    assert "https://fastapi.tiangolo.com" in csp
    assert "https://fonts.googleapis.com" in csp
    assert "https://fonts.gstatic.com" in csp
    assert "connect-src 'self' https://cdn.jsdelivr.net" in csp


def test_security_headers_middleware_preserves_custom_csp() -> None:
    """Explicit Content-Security-Policy set by a handler is preserved."""
    app = Starlette(routes=[Route("/custom", _custom_csp_endpoint)])
    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)

    resp = client.get("/custom")
    assert resp.status_code == 200
    assert resp.headers["Content-Security-Policy"] == "default-src 'self'"


def test_create_app_docs_endpoints_have_docs_csp() -> None:
    """FastAPI docs endpoints (/api/docs and /api/redoc) allow CDN assets."""
    client = TestClient(create_app())

    docs_resp = client.get("/api/docs")
    assert docs_resp.status_code == 200
    docs_csp = docs_resp.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in docs_csp
    assert "'unsafe-inline'" in docs_csp

    redoc_resp = client.get("/api/redoc")
    assert redoc_resp.status_code == 200
    redoc_csp = redoc_resp.headers["Content-Security-Policy"]
    assert "https://cdn.jsdelivr.net" in redoc_csp
    assert "'unsafe-inline'" in docs_csp

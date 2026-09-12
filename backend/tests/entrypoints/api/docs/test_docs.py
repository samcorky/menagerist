from starlette.testclient import TestClient

from app.entrypoints.api import create_app


def test_swagger_documentation_endpoint() -> None:
    """Swagger UI documentation page is served with custom favicon and title."""
    client = TestClient(create_app())
    response = client.get("/api/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]
    assert "/api/docs/favicon.svg" in response.text
    assert "Swagger UI" in response.text
    assert "/api/openapi.json" in response.text


def test_swagger_oauth2_redirect_endpoint() -> None:
    """Swagger UI OAuth2 redirect page is served."""
    client = TestClient(create_app())
    response = client.get("/api/docs/oauth2-redirect")

    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]


def test_redoc_documentation_endpoint() -> None:
    """ReDoc documentation page is served with custom favicon and title."""
    client = TestClient(create_app())
    response = client.get("/api/redoc")

    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]
    assert "/api/docs/favicon.svg" in response.text
    assert "ReDoc" in response.text
    assert "/api/openapi.json" in response.text


def test_favicon_endpoints() -> None:
    """Favicon SVG is served with image/svg+xml media type."""
    client = TestClient(create_app())

    response_docs = client.get("/api/docs/favicon.svg")
    assert response_docs.status_code == 200
    assert response_docs.headers["Content-Type"] == "image/svg+xml"
    assert "<svg" in response_docs.text

    response_ico = client.get("/api/favicon.ico")
    assert response_ico.status_code == 200
    assert response_ico.headers["Content-Type"] == "image/svg+xml"
    assert "<svg" in response_ico.text


def test_logo_endpoint() -> None:
    """Logo SVG is served with image/svg+xml media type."""
    client = TestClient(create_app())
    response = client.get("/api/docs/logo.svg")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/svg+xml"
    assert "<svg" in response.text


def test_openapi_schema_contains_x_logo() -> None:
    """OpenAPI schema contains the x-logo vendor extension pointing to docs logo."""
    app = create_app()
    schema = app.openapi()

    assert "x-logo" in schema["info"]
    assert schema["info"]["x-logo"]["url"] == "/api/docs/logo.svg"
    assert "logo" in schema["info"]["x-logo"]["altText"]

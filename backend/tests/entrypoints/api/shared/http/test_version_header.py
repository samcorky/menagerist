from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.platform.app_info import load_app_info


def test_app_version_header_present_on_successful_response() -> None:
    """App-Version header is present on 200 responses and matches the app version."""
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert "App-Version" in response.headers
    assert response.headers["App-Version"] == load_app_info().version


def test_app_version_header_present_on_not_found() -> None:
    """App-Version header is present even when the route does not exist."""
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get("/api/does-not-exist")
    assert "App-Version" in response.headers


def test_app_version_header_present_on_openapi_schema() -> None:
    """App-Version header is present on the OpenAPI schema endpoint."""
    client = TestClient(create_app())
    response = client.get("/api/openapi.json")
    assert "App-Version" in response.headers

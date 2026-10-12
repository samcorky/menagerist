import importlib
import inspect
import json
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.docs.router import etag_matches, render_swagger_page
from app.entrypoints.api.openapi import _DESCRIPTION_PATH, api_description
from app.platform.config import get_identity_settings


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


def test_openapi_schema_renames_multipart_body_schemas() -> None:
    """Auto-generated Body_<operation_id> schemas are renamed, title included.

    The `title` must be rewritten alongside the `components.schemas` key,
    since Swagger UI and generated clients display the schema's `title`
    rather than its key.
    """
    app = create_app()
    schema = app.openapi()
    schemas = schema["components"]["schemas"]

    assert not any(name.startswith("Body_") for name in schemas)
    assert schemas["StageMediaBody"]["title"] == "StageMediaBody"
    assert schemas["UploadAndAttachMediaBody"]["title"] == "UploadAndAttachMediaBody"


def test_swagger_page_references_init_script_and_csrf_cookie_name() -> None:
    """The page loads our setup script and gets the CSRF cookie name from settings."""
    client = TestClient(create_app())
    response = client.get("/api/docs")

    assert response.status_code == 200
    assert 'src="/api/docs/swagger-init.js?v=' in response.text
    assert f'data-csrf-cookie="{get_identity_settings().csrf_cookie_name}"' in (
        response.text
    )
    assert "swagger-ui-dist@5.33.0/" in response.text
    assert "/api/docs/favicon.svg" in response.text


@pytest.mark.parametrize(("path", "expected"), [("/api/docs", 2), ("/api/redoc", 1)])
def test_docs_external_assets_are_pinned_and_have_integrity(
    path: str, expected: int
) -> None:
    """Every external script or stylesheet has an exact version and SRI hash."""
    html = TestClient(create_app()).get(path).text
    tags = re.findall(r"<(?:script|link)[^>]*>", html)
    external = [t for t in tags if re.search(r'(?:src|href)="https?://', t)]

    assert len(external) == expected
    for tag in external:
        assert re.search(r'(?:src|href)="https://[^"]+@\d+\.\d+\.\d+/', tag), tag
        assert re.search(r'integrity="sha384-[A-Za-z0-9+/]{64}"', tag), tag
        assert 'crossorigin="anonymous"' in tag, tag


def test_swagger_page_csp_allows_script_without_unsafe_eval() -> None:
    """The docs CSP covers our same-origin script and never allows eval."""
    client = TestClient(create_app())
    csp = client.get("/api/docs").headers["Content-Security-Policy"]

    assert "script-src 'self'" in csp
    assert "unsafe-eval" not in csp


def test_swagger_init_script_is_served() -> None:
    """The setup script is public JavaScript cached immutably (URL is versioned)."""
    client = TestClient(create_app())
    response = client.get("/api/docs/swagger-init.js")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/javascript")
    assert response.headers["Cache-Control"] == ("public, max-age=31536000, immutable")
    assert "X-CSRF-Token" in response.text
    assert "unsafe-eval" not in response.headers["Content-Security-Policy"]


def test_openapi_has_no_csrf_header_parameter_and_explains_sign_in() -> None:
    """The CSRF header stays out of the schema; the description explains sign-in."""
    schema = create_app().openapi()

    assert "x-csrf-token" not in json.dumps(schema["paths"]).lower()
    assert "x-csrf-token" not in json.dumps(schema["components"]).lower()
    for operations in schema["paths"].values():
        for operation in operations.values():
            names = [p["name"].lower() for p in operation.get("parameters", [])]
            assert "x-csrf-token" not in names
    assert "POST /api/v1/auth/login" in schema["info"]["description"]
    assert "is read-only" in schema["info"]["description"]


def test_swagger_page_is_revalidated_with_a_strong_etag() -> None:
    """The page carries an ETag and answers a matching If-None-Match with 304."""
    client = TestClient(create_app())
    first = client.get("/api/docs")
    etag = first.headers["ETag"]

    assert etag.startswith('"')
    assert first.headers["Cache-Control"] == "no-cache"
    assert "Content-Security-Policy" in first.headers

    second = client.get("/api/docs", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.headers["ETag"] == etag
    assert client.get("/api/docs").headers["ETag"] == etag


def test_swagger_page_references_versioned_init_script() -> None:
    """The script URL carries a content-hash query so a new release busts the cache."""
    client = TestClient(create_app())

    assert re.search(
        r'src="/api/docs/swagger-init\.js\?v=[0-9a-f]{12}"',
        client.get("/api/docs").text,
    )


def test_swagger_template_escapes_values() -> None:
    """Hostile titles and cookie names cannot break out of the markup."""
    hostile = '"><script>alert(1)</script>'
    html = render_swagger_page(
        title=hostile, csrf_cookie_name=hostile, init_js_version="abc"
    )

    assert "<script>alert(1)" not in html
    assert "&quot;&gt;&lt;script&gt;" in html


def test_swagger_template_placeholders_match_supplied_values() -> None:
    """The template uses exactly the placeholders the code supplies."""
    template = (
        Path(inspect.getfile(render_swagger_page)).parent / "templates" / "swagger.html"
    )
    in_template = set(
        re.findall(r"\$([a-z0-9_]+)", template.read_text(encoding="utf-8"))
    )
    html = render_swagger_page(title="t", csrf_cookie_name="c", init_js_version="v")

    assert in_template == {
        "swagger_css_url",
        "swagger_js_url",
        "swagger_css_integrity",
        "swagger_js_integrity",
        "favicon_url",
        "title",
        "init_js_url",
        "csrf_cookie_name",
        "openapi_url",
        "oauth2_redirect_url",
    }
    assert "$" not in html


def test_etag_matches_handles_weak_lists_and_wildcard() -> None:
    """If-None-Match is parsed as a list with weak comparison and `*`."""
    etag = '"abc"'

    assert etag_matches('"abc"', etag)
    assert etag_matches('W/"abc"', etag)
    assert etag_matches('"zzz", W/"abc"', etag)
    assert etag_matches("*", etag)
    assert not etag_matches('"other"', etag)
    assert not etag_matches(None, etag)


def test_documents_answer_304_for_weak_and_wildcard_validators() -> None:
    """Both the page and the schema honour the parsed validators."""
    client = TestClient(create_app())
    page_etag = client.get("/api/docs").headers["ETag"]
    schema_etag = client.get("/api/openapi.json").headers["ETag"]
    weak_page = {"If-None-Match": f"W/{page_etag}"}
    multi_schema = {"If-None-Match": f'"x", W/{schema_etag}'}

    assert client.get("/api/docs", headers=weak_page).status_code == 304
    assert client.get("/api/docs", headers={"If-None-Match": "*"}).status_code == 304
    assert client.get("/api/openapi.json", headers=multi_schema).status_code == 304


def test_swagger_etag_changes_when_the_template_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ETag is a hash of the rendered page, so a new template busts it."""
    docs_router = importlib.import_module("app.entrypoints.api.docs.router")

    docs_router._swagger_body.cache_clear()
    original = docs_router._swagger_body("T")[1]
    changed = tmp_path / "swagger.html"
    changed.write_text("<p>$title $csrf_cookie_name</p>", encoding="utf-8")
    monkeypatch.setattr(docs_router, "_TEMPLATE_PATH", changed)
    docs_router._swagger_body.cache_clear()
    try:
        assert docs_router._swagger_body("T")[1] != original
    finally:
        monkeypatch.undo()
        docs_router._swagger_body.cache_clear()


def test_openapi_etag_is_a_content_hash_that_follows_the_schema() -> None:
    """The ETag changes with the schema; only a matching hash gets a 304."""
    app = create_app()
    client = TestClient(app)
    first = client.get("/api/openapi.json")
    etag = first.headers["ETag"]

    assert etag != f'"{app.version}"'
    assert first.headers["Cache-Control"] == "no-cache"
    assert client.get("/api/openapi.json").headers["ETag"] == etag
    assert (
        client.get("/api/openapi.json", headers={"If-None-Match": etag}).status_code
        == 304
    )

    changed = {**app.openapi(), "info": {**app.openapi()["info"], "description": "new"}}
    app.openapi_schema = changed
    after = client.get("/api/openapi.json", headers={"If-None-Match": etag})

    assert after.status_code == 200
    assert after.headers["ETag"] != etag
    assert after.json()["info"]["description"] == "new"


def test_openapi_has_summary_and_sectioned_description() -> None:
    """The tagline is the summary; the description has the sections in order."""
    info = create_app().openapi()["info"]
    description = info["description"]

    assert info["summary"]
    assert info["summary"] not in description
    headings = re.findall(r"^## (.+)$", description, flags=re.MULTILINE)
    assert headings == ["About", "Signing in", "Permissions", "Errors"]
    settings = get_identity_settings()
    assert settings.csrf_cookie_name in description
    assert settings.cookie_name in description
    for word in ("node", "edge", "graph", "shelf"):
        assert not re.search(rf"\b{word}s?\b", description, flags=re.IGNORECASE)


def test_every_tag_description_is_one_short_plain_line() -> None:
    """Tag descriptions sit beside the tag title, so they stay short single lines."""
    for tag in create_app().openapi()["tags"]:
        text = tag["description"]
        assert "\n" not in text, tag["name"]
        assert len(text) <= 80, tag["name"]


def test_signing_in_section_explains_sessions_and_csrf() -> None:
    """The long description carries the cookie and CSRF explanation."""
    description = create_app().openapi()["info"]["description"]

    assert "X-CSRF-Token" in description
    assert "csrf_failed" in description


def test_api_description_placeholders_match_supplied_values() -> None:
    """The description file uses exactly the placeholders the code supplies."""
    in_file = set(re.findall(r"\$([a-z_]+)", _DESCRIPTION_PATH.read_text("utf-8")))

    assert in_file == {"session_cookie_name", "csrf_cookie_name"}
    assert "$" not in api_description()


@pytest.mark.parametrize(
    ("method", "path", "statuses"),
    [
        ("post", "/api/v1/auth/login", {"401", "403", "429"}),
        ("post", "/api/v1/auth/password", {"400", "401", "429"}),
        ("patch", "/api/v1/auth/me", {"400", "401", "422"}),
        ("post", "/api/v1/user/{user_id}/unlock", {"404"}),
    ],
)
def test_openapi_documents_auth_error_responses(
    method: str, path: str, statuses: set[str]
) -> None:
    """Sign-in, password, profile and unlock errors appear in the schema."""
    schema = TestClient(create_app()).get("/api/openapi.json").json()
    responses = schema["paths"][path][method]["responses"]

    assert statuses <= set(responses)
    for status in statuses - {"422"}:
        assert "application/problem+json" in responses[status]["content"]


@pytest.mark.parametrize("path", ["/api/v1/auth/login", "/api/v1/auth/password"])
def test_openapi_throttled_response_documents_retry_after(path: str) -> None:
    """The 429 answer lists the `Retry-After` header."""
    schema = TestClient(create_app()).get("/api/openapi.json").json()
    headers = schema["paths"][path]["post"]["responses"]["429"]["headers"]

    assert headers["Retry-After"]["schema"] == {"type": "integer"}

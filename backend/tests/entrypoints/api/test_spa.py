from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.spa import SpaStaticFiles
from app.platform.config import get_api_settings

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_SHELL_HTML = "<html>shell</html>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A miniature adapter-static build."""
    (tmp_path / "200.html").write_text(_SHELL_HTML)
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path / "_app" / "immutable").mkdir(parents=True)
    (tmp_path / "_app" / "immutable" / "entry.abc123.js").write_text("console.log(1)")
    (tmp_path / ".well-known").mkdir()
    (tmp_path / ".well-known" / "security.txt").write_text("Contact: nobody")
    (tmp_path / ".secret").write_text("nope")
    return tmp_path


@pytest.fixture
def client(dist: Path) -> TestClient:
    """The SPA static app on its own, without the rest of the API."""
    app = Starlette(routes=[Mount("/", SpaStaticFiles(directory=dist))])
    return TestClient(app)


@pytest.fixture
def app_client(dist: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real `create_app()` with the SPA enabled through its setting."""
    monkeypatch.setenv("MENAGERIST_FRONTEND_DIST_PATH", str(dist))
    get_api_settings.cache_clear()
    yield TestClient(create_app())
    get_api_settings.cache_clear()


@pytest.mark.parametrize("path", ["/", "/explore", "/node/123/edit", "/a/b/c/d"])
def test_client_side_routes_get_the_spa_shell(client: TestClient, path: str) -> None:
    """Anything that is not a real file is a client-side route: serve the shell."""
    resp = client.get(path)

    assert resp.status_code == 200
    assert resp.text == _SHELL_HTML


def test_shell_is_never_cached_and_carries_the_spa_csp(client: TestClient) -> None:
    """The shell must always be fresh and allow the SPA's own scripts and styles."""
    resp = client.get("/")

    assert resp.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
    assert (
        "script-src 'self' 'unsafe-inline'" in resp.headers["Content-Security-Policy"]
    )
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_requesting_the_shell_file_directly_gets_shell_headers(
    client: TestClient,
) -> None:
    """`/200.html` is the shell, so it gets the shell's no-store policy too."""
    resp = client.get("/200.html")

    assert resp.text == _SHELL_HTML
    assert resp.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"


def test_hashed_assets_are_cached_for_a_year_and_immutable(client: TestClient) -> None:
    """Content-hashed files never change, so browsers may keep them forever."""
    resp = client.get("/_app/immutable/entry.abc123.js")

    assert resp.status_code == 200
    assert resp.headers.get_list("Cache-Control") == [
        "public, max-age=31536000, immutable"
    ]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_other_files_get_a_short_cache(client: TestClient) -> None:
    """Unhashed files (icons, etc.) are cached briefly, not forever."""
    resp = client.get("/favicon.svg")

    assert resp.status_code == 200
    assert resp.headers.get_list("Cache-Control") == ["public, max-age=3600"]


@pytest.mark.parametrize("path", ["/missing.js", "/_app/immutable/gone.deadbeef.js"])
def test_missing_assets_are_404_not_the_shell(client: TestClient, path: str) -> None:
    """A stale asset URL must fail loudly rather than return HTML as JavaScript."""
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/.secret", "/.git/config", "/.env"])
def test_dotfiles_are_hidden(client: TestClient, path: str) -> None:
    """Hidden files are never served, even if they exist in the build directory."""
    assert client.get(path).status_code == 404


def test_well_known_is_the_one_allowed_dot_directory(client: TestClient) -> None:
    """`/.well-known/` stays reachable for standard discovery files."""
    resp = client.get("/.well-known/security.txt")

    assert resp.status_code == 200
    assert resp.text == "Contact: nobody"


def test_favicon_ico_redirects_to_the_svg(client: TestClient) -> None:
    """Browsers ask for /favicon.ico; the build ships an SVG."""
    resp = client.get("/favicon.ico", follow_redirects=False)

    assert resp.status_code == 301
    assert resp.headers["Location"] == "/favicon.svg"


def test_unknown_api_paths_are_404_never_the_shell(client: TestClient) -> None:
    """A mistyped API URL must not come back as a 200 HTML page."""
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/api").status_code == 404


def test_only_get_and_head_are_allowed(client: TestClient) -> None:
    """The static app is read-only."""
    assert client.post("/").status_code == 405


def test_the_spa_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the setting the process is API-only: no shell, just 404s."""
    monkeypatch.delenv("MENAGERIST_FRONTEND_DIST_PATH", raising=False)
    get_api_settings.cache_clear()
    try:
        resp = TestClient(create_app()).get("/")
    finally:
        get_api_settings.cache_clear()

    assert resp.status_code == 404


def test_create_app_serves_the_spa_alongside_the_api(app_client: TestClient) -> None:
    """With the setting on, the API keeps its routes and the SPA takes the rest."""
    assert app_client.get("/api/health").status_code == 200
    assert app_client.get("/explore").text == _SHELL_HTML
    assert app_client.get("/api/does-not-exist").status_code == 404


def test_api_responses_keep_their_own_security_headers(app_client: TestClient) -> None:
    """The SPA's relaxed CSP applies to the shell only, never to API responses."""
    api = app_client.get("/api/health")
    shell = app_client.get("/")

    assert "default-src 'none'" in api.headers["Content-Security-Policy"]
    assert "default-src 'self'" in shell.headers["Content-Security-Policy"]


def test_a_missing_dist_directory_fails_at_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong path is a deployment error: fail immediately, not on first request."""
    monkeypatch.setenv("MENAGERIST_FRONTEND_DIST_PATH", str(tmp_path / "nope"))
    get_api_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="does not exist"):
            create_app()
    finally:
        get_api_settings.cache_clear()

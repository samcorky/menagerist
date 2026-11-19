"""The SPA shell's link-preview tags follow the instance's branding (#598)."""

import gzip
from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.spa import SpaStaticFiles, brand_shell
from app.modules.system.domain.branding import Branding
from app.platform.config import get_api_settings

if TYPE_CHECKING:
    from pathlib import Path

# The preview tags as frontend/src/app.html ships them.
SHELL = """<!doctype html>
<html lang="en">
	<head>
		<meta
			name="description"
			content="A self-hostable platform for organising the things you care about."
		/>
		<meta property="og:site_name" content="Menagerist" />
		<meta property="og:title" content="Menagerist" />
		<meta
			property="og:description"
			content="A self-hostable platform for organising the things you care about."
		/>
		<meta property="og:type" content="website" />
		<meta property="og:image" content="/share-image.png" />
		<meta property="og:image:alt" content="The Menagerist mark beside its name." />
		<meta name="apple-mobile-web-app-title" content="Menagerist" />
	</head>
	<body>Menagerist</body>
</html>
"""
HOARD = Branding(
    name="The Hoard", short_name="Hoard", description="Our family's things."
)


def test_the_preview_names_and_describes_the_instance() -> None:
    """Title, site name and both descriptions come from the branding."""
    html = brand_shell(SHELL, HOARD, origin=None, path="/")

    assert '<meta property="og:title" content="The Hoard" />' in html
    assert '<meta property="og:site_name" content="The Hoard" />' in html
    assert 'name="description"\n\t\t\tcontent="Our family&#x27;s things."' in html
    assert (
        'property="og:description"\n\t\t\tcontent="Our family&#x27;s things."' in html
    )


def test_only_the_preview_tags_change() -> None:
    """The app's own name elsewhere in the page is left alone (#641)."""
    html = brand_shell(SHELL, HOARD, origin=None, path="/")

    assert '<meta name="apple-mobile-web-app-title" content="Menagerist" />' in html
    assert "<body>Menagerist</body>" in html
    assert 'content="The Menagerist mark beside its name."' in html


def test_values_are_escaped() -> None:
    """An administrator's text cannot break out of the attribute."""
    branding = Branding(name='"><script>x</script>', description="a & b <c>")

    html = brand_shell(SHELL, branding, origin=None, path="/")

    assert "<script>x</script>" not in html
    assert 'content="&quot;&gt;&lt;script&gt;x&lt;/script&gt;"' in html
    assert "a &amp; b &lt;c&gt;" in html


def test_without_a_public_origin_urls_stay_relative() -> None:
    """With no origin configured the image stays relative and there is no og:url."""
    html = brand_shell(SHELL, HOARD, origin=None, path="/items/1")

    assert '<meta property="og:image" content="/share-image.png" />' in html
    assert "og:url" not in html


def test_with_a_public_origin_urls_are_absolute() -> None:
    """Link previews that need a full address (WhatsApp, Facebook, X) get one."""
    html = brand_shell(
        SHELL, HOARD, origin="https://hoard.example.com/", path="/items/1"
    )

    image = "https://hoard.example.com/share-image.png"
    assert f'<meta property="og:image" content="{image}" />' in html
    assert (
        '<meta property="og:url" content="https://hoard.example.com/items/1" />' in html
    )


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A build holding only the shell."""
    (tmp_path / "200.html").write_bytes(SHELL.encode())
    (tmp_path / "200.html.gz").write_bytes(gzip.compress(SHELL.encode()))
    return tmp_path


def _client(dist: Path, branding: Branding, origin: str | None = None) -> TestClient:
    async def current() -> Branding:
        return branding

    spa = SpaStaticFiles(directory=dist, branding=current, public_origin=origin)
    return TestClient(Starlette(routes=[Mount("/", spa)]))


@pytest.mark.parametrize("path", ["/", "/items/1", "/200.html"])
def test_every_shell_response_is_branded(dist: Path, path: str) -> None:
    """Client-side routes and the shell file itself carry the branded tags."""
    response = _client(dist, HOARD).get(path)

    assert response.status_code == 200
    assert '<meta property="og:title" content="The Hoard" />' in response.text
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"
    assert response.headers["content-type"].startswith("text/html")


def test_the_build_s_compressed_shell_is_not_served_stale(dist: Path) -> None:
    """The precompressed copy holds the unbranded tags, so it is never sent."""
    response = _client(dist, HOARD).get("/items/1", headers={"Accept-Encoding": "gzip"})

    assert "content-encoding" not in response.headers
    assert "The Hoard" in response.text


def test_the_app_compresses_the_branded_shell(
    dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the whole app, the compression middleware encodes the branded page."""
    monkeypatch.setenv("MENAGERIST_API_FRONTEND_DIST_PATH", str(dist))
    get_api_settings.cache_clear()
    try:
        response = TestClient(create_app()).get(
            "/items/1", headers={"Accept-Encoding": "gzip"}
        )
    finally:
        get_api_settings.cache_clear()

    assert response.headers["content-encoding"] == "gzip"
    assert '<meta property="og:title" content="Menagerist" />' in response.text
    assert "og:description" in response.text


def test_the_shell_follows_a_changed_name(dist: Path) -> None:
    """The branding is read per request, so a saved name shows on the next load."""
    names = iter(["First", "Second"])

    async def current() -> Branding:
        return Branding(name=next(names), description="d")

    client = TestClient(
        Starlette(routes=[Mount("/", SpaStaticFiles(directory=dist, branding=current))])
    )

    assert 'content="First"' in client.get("/").text
    assert 'content="Second"' in client.get("/").text


def test_without_branding_the_shell_is_served_as_built(dist: Path) -> None:
    """A static mount with no branding source changes nothing."""
    client = TestClient(Starlette(routes=[Mount("/", SpaStaticFiles(directory=dist))]))

    assert client.get("/", headers={"Accept-Encoding": "identity"}).text == SHELL

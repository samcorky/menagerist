"""The SPA shell's marked tags follow the instance's branding (#598)."""

import gzip
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shell_branding import ShellTemplate, UnknownBrandingFieldError
from app.entrypoints.api.spa import SpaStaticFiles
from app.modules.system.domain.branding import Branding
from app.platform.config import get_api_settings

APP_HTML = Path(__file__).parents[4] / "frontend" / "src" / "app.html"

# Marked as frontend/src/app.html marks them, formatted two ways on purpose.
SHELL = """<!doctype html>
<html lang="en">
	<head>
		<meta
			name="description"
			content="A self-hostable platform."
			data-branding="description"
		/>
		<meta property="og:site_name" content="Menagerist" data-branding="name" />
		<meta data-branding="name" content="Menagerist" property="og:title">
		<meta property="og:url" content="/" data-branding="page-url" />
		<meta property="og:type" content="website" />
		<meta
			property="og:image"
			content="/app-share-image.png"
			data-branding="versioned-url" />
		<meta property="og:image:alt" content="The Menagerist mark beside its name." />
		<meta name="apple-mobile-web-app-title" content="Menagerist" />
		<script>if (a < b && "<meta data-branding=\\"name\\">") {}</script>
	</head>
	<body>Menagerist</body>
</html>
"""
HOARD = Branding(
    name="The Hoard", short_name="Hoard", description="Our family's things."
)


def render(
    origin: str | None = None, path: str = "/", version: str | None = None
) -> str:
    """The test shell filled in for The Hoard."""
    return ShellTemplate(SHELL).render(HOARD, origin=origin, path=path, version=version)


def test_marked_tags_take_the_branding_however_they_are_written() -> None:
    """Attribute order, line breaks and self-closing slashes make no difference."""
    html = render()

    assert '<meta property="og:site_name" content="The Hoard" />' in html
    assert '<meta content="The Hoard" property="og:title">' in html
    assert '<meta name="description" content="Our family&#x27;s things." />' in html


def test_the_marker_is_not_sent() -> None:
    """The server's own bookkeeping stays out of the page it fills in."""
    assert 'data-branding="' not in render().split("<script>")[0]


def test_everything_else_is_left_as_it_was() -> None:
    """Unmarked tags, scripts and the body pass through byte for byte (#641)."""
    html = render()

    assert '<meta name="apple-mobile-web-app-title" content="Menagerist" />' in html
    assert 'content="The Menagerist mark beside its name."' in html
    assert '<script>if (a < b && "<meta data-branding=\\"name\\">") {}</script>' in html
    assert "<body>Menagerist</body>" in html


def test_values_are_escaped() -> None:
    """An administrator's text cannot break out of the attribute."""
    branding = Branding(name='"><script>x</script>', description="a & b <c>")

    html = ShellTemplate(SHELL).render(branding, origin=None, path="/")

    assert "<script>x</script>" not in html
    assert 'content="&quot;&gt;&lt;script&gt;x&lt;/script&gt;"' in html
    assert 'content="a &amp; b &lt;c&gt;"' in html


def test_without_a_public_origin_urls_stay_relative() -> None:
    """The image keeps its relative path and the page's own address is left out."""
    html = render(path="/items/1")

    assert '<meta property="og:image" content="/app-share-image.png" />' in html
    assert "og:url" not in html


def test_with_a_public_origin_urls_are_absolute() -> None:
    """Link previews that need a full address (WhatsApp, Facebook, X) get one."""
    html = render(origin="https://hoard.example.com/", path="/items/1")

    image = "https://hoard.example.com/app-share-image.png"
    assert f'<meta property="og:image" content="{image}" />' in html
    page = "https://hoard.example.com/items/1"
    assert f'<meta property="og:url" content="{page}" />' in html


def test_the_image_address_carries_the_build_version() -> None:
    """A crawler that caches the image by address fetches it again per release."""
    html = render(origin="https://hoard.example.com", version="0.2026.11.5")

    image = "https://hoard.example.com/app-share-image.png?v=0.2026.11.5"
    assert f'<meta property="og:image" content="{image}" />' in html


def test_the_version_in_the_image_address_is_escaped() -> None:
    """A version with a plus or a space cannot break the address."""
    html = render(version="1.0+build 7")

    assert 'content="/app-share-image.png?v=1.0%2Bbuild%207"' in html


def test_an_unknown_marker_fails_loudly() -> None:
    """A typo in app.html is an error, not a tag silently left unfilled."""
    with pytest.raises(UnknownBrandingFieldError, match="nmae"):
        ShellTemplate('<meta property="og:title" content="x" data-branding="nmae" />')


def test_the_real_app_html_marks_every_preview_tag() -> None:
    """frontend/src/app.html fills the preview's name, description and addresses."""
    template = ShellTemplate(APP_HTML.read_text(encoding="utf-8"))

    html = template.render(HOARD, origin="https://hoard.example.com", path="/items/1")

    assert template.fields == {"name", "description", "versioned-url", "page-url"}
    image = "https://hoard.example.com/app-share-image.png"
    for tag in (
        '<meta property="og:site_name" content="The Hoard" />',
        '<meta property="og:title" content="The Hoard" />',
        '<meta name="description" content="Our family&#x27;s things." />',
        '<meta property="og:description" content="Our family&#x27;s things." />',
        '<meta property="og:url" content="https://hoard.example.com/items/1" />',
        f'<meta property="og:image" content="{image}" />',
    ):
        assert tag in html
    assert "%sveltekit.head%" in html  # the build's own placeholders pass through


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A build holding only the shell, with a precompressed copy as the build makes."""
    (tmp_path / "200.html").write_bytes(SHELL.encode())
    (tmp_path / "200.html.gz").write_bytes(gzip.compress(SHELL.encode()))
    return tmp_path


def _client(
    dist: Path,
    branding: Branding,
    origin: str | None = None,
    version: str | None = None,
) -> TestClient:
    async def current() -> Branding:
        return branding

    spa = SpaStaticFiles(
        directory=dist, branding=current, public_origin=origin, version=version
    )
    return TestClient(Starlette(routes=[Mount("/", spa)]))


@pytest.mark.parametrize("path", ["/", "/items/1", "/200.html"])
def test_every_shell_response_is_branded(dist: Path, path: str) -> None:
    """Client-side routes and the shell file itself carry the branded tags."""
    response = _client(dist, HOARD).get(path)

    assert response.status_code == 200
    assert '<meta property="og:site_name" content="The Hoard" />' in response.text
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"
    assert response.headers["content-type"].startswith("text/html")


def test_the_served_shell_names_the_image_by_build_version(dist: Path) -> None:
    """The version the server was started with reaches the served page's image tag."""
    response = _client(dist, HOARD, version="0.2026.11.5").get("/items/1")

    assert 'content="/app-share-image.png?v=0.2026.11.5"' in response.text


def test_the_build_s_compressed_shell_is_not_served_stale(dist: Path) -> None:
    """The precompressed copy holds the defaults, so it is never sent."""
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
    assert '<meta property="og:site_name" content="Menagerist" />' in response.text


def test_the_shell_follows_a_changed_name(dist: Path) -> None:
    """The branding is read per request, so a saved name shows on the next load."""
    names = iter(["First", "Second"])

    async def current() -> Branding:
        return Branding(name=next(names), description="d")

    client = TestClient(
        Starlette(routes=[Mount("/", SpaStaticFiles(directory=dist, branding=current))])
    )

    assert 'og:site_name" content="First"' in client.get("/").text
    assert 'og:site_name" content="Second"' in client.get("/").text


def test_without_branding_the_shell_is_served_as_built(dist: Path) -> None:
    """A static mount with no branding source changes nothing."""
    client = TestClient(Starlette(routes=[Mount("/", SpaStaticFiles(directory=dist))]))

    assert client.get("/", headers={"Accept-Encoding": "identity"}).text == SHELL

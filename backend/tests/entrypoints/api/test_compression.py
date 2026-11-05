"""Responses are compressed: the SPA from the build, everything else on the fly."""

import gzip
from typing import TYPE_CHECKING

import brotli  # type: ignore[import-untyped]
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.spa import SpaStaticFiles
from app.platform.config import get_api_settings

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_ASSET = "_app/immutable/entry.abc123.js"
_BIG_JS = "console.log('menagerist');\n" * 400
# Each sibling decodes to different text, so the body shows which one was served.
_BROTLI_TEXT = "from the brotli file"
_GZIP_TEXT = "from the gzip file"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A miniature adapter-static build with precompressed stand-ins."""
    (tmp_path / "200.html").write_text("<html>shell</html>")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path / "_app" / "immutable").mkdir(parents=True)
    (tmp_path / _ASSET).write_text("console.log(1)")
    return tmp_path


def _precompress(dist: Path, name: str) -> None:
    (dist / f"{name}.br").write_bytes(brotli.compress(_BROTLI_TEXT.encode()))
    (dist / f"{name}.gz").write_bytes(gzip.compress(_GZIP_TEXT.encode()))


@pytest.fixture
def spa(dist: Path) -> TestClient:
    """The SPA static app on its own, so only its own serving is under test."""
    return TestClient(Starlette(routes=[Mount("/", SpaStaticFiles(directory=dist))]))


@pytest.fixture
def app_client(dist: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real `create_app()` with the SPA enabled, middleware included."""
    monkeypatch.setenv("MENAGERIST_API_FRONTEND_DIST_PATH", str(dist))
    get_api_settings.cache_clear()
    yield TestClient(create_app())
    get_api_settings.cache_clear()


@pytest.mark.parametrize(
    ("accept", "encoding", "text"),
    [
        ("br, gzip", "br", _BROTLI_TEXT),
        ("gzip", "gzip", _GZIP_TEXT),
        ("gzip, br;q=0", "gzip", _GZIP_TEXT),
    ],
)
def test_precompressed_sibling_is_served_when_accepted(
    spa: TestClient, dist: Path, accept: str, encoding: str, text: str
) -> None:
    """A `.br`/`.gz` file beside the asset is sent as is, with the asset's type."""
    _precompress(dist, _ASSET)

    resp = spa.get(f"/{_ASSET}", headers={"Accept-Encoding": accept})

    assert resp.status_code == 200
    assert resp.text == text
    assert resp.headers["content-encoding"] == encoding
    assert resp.headers["content-type"].startswith("text/javascript")
    assert resp.headers["vary"] == "Accept-Encoding"
    assert "immutable" in resp.headers["cache-control"]


def test_plain_file_is_served_when_no_encoding_is_accepted(
    spa: TestClient, dist: Path
) -> None:
    """A client that accepts neither coding gets the original, marked as varying."""
    _precompress(dist, _ASSET)

    resp = spa.get(f"/{_ASSET}", headers={"Accept-Encoding": "identity"})

    assert resp.content == b"console.log(1)"
    assert "content-encoding" not in resp.headers
    assert resp.headers["vary"] == "Accept-Encoding"


def test_file_without_a_sibling_is_unchanged(spa: TestClient) -> None:
    """No precompressed file, no `Vary` and no encoding."""
    resp = spa.get("/favicon.svg", headers={"Accept-Encoding": "br"})

    assert resp.text == "<svg/>"
    assert "content-encoding" not in resp.headers
    assert "vary" not in resp.headers


def test_range_request_gets_the_plain_file(spa: TestClient, dist: Path) -> None:
    """Part of a compressed file is no use to the client, so ranges stay plain."""
    _precompress(dist, _ASSET)

    resp = spa.get(
        f"/{_ASSET}", headers={"Accept-Encoding": "br", "Range": "bytes=0-6"}
    )

    assert resp.status_code == 206
    assert resp.content == b"console"
    assert "content-encoding" not in resp.headers


def test_precompressed_shell_keeps_its_headers(spa: TestClient, dist: Path) -> None:
    """The shell is precompressed too, and still never cached, with its CSP."""
    _precompress(dist, "200.html")

    resp = spa.get("/explore", headers={"Accept-Encoding": "br"})

    assert resp.text == _BROTLI_TEXT
    assert resp.headers["content-encoding"] == "br"
    assert resp.headers["content-type"].startswith("text/html")
    assert "no-store" in resp.headers["cache-control"]
    assert "default-src 'self'" in resp.headers["content-security-policy"]


def test_conditional_request_matches_the_compressed_variant(
    spa: TestClient, dist: Path
) -> None:
    """Each encoding has its own ETag, so revalidating the variant gives a 304."""
    _precompress(dist, _ASSET)
    first = spa.get(f"/{_ASSET}", headers={"Accept-Encoding": "br"})

    again = spa.get(
        f"/{_ASSET}",
        headers={"Accept-Encoding": "br", "If-None-Match": first.headers["etag"]},
    )

    assert again.status_code == 304


def test_app_compresses_text_but_not_media(app_client: TestClient, dist: Path) -> None:
    """Without a precompressed file, text is compressed on the fly; images are not."""
    (dist / "big.js").write_text(_BIG_JS)
    (dist / "photo.png").write_bytes(_BIG_JS.encode())

    text = app_client.get("/big.js", headers={"Accept-Encoding": "gzip"})
    image = app_client.get("/photo.png", headers={"Accept-Encoding": "gzip"})

    assert text.headers["content-encoding"] == "gzip"
    assert text.text == _BIG_JS
    assert "content-encoding" not in image.headers
    assert image.content == _BIG_JS.encode()


def test_compressing_a_static_file_keeps_its_strong_etag(
    app_client: TestClient, dist: Path
) -> None:
    """A file's ETag is the same whether or not it is compressed on the way out."""
    (dist / "big.js").write_text(_BIG_JS)

    plain = app_client.get("/big.js", headers={"Accept-Encoding": "identity"})
    packed = app_client.get("/big.js", headers={"Accept-Encoding": "gzip"})

    assert packed.headers["content-encoding"] == "gzip"
    assert not plain.headers["etag"].startswith("W/")
    assert packed.headers["etag"] == plain.headers["etag"]


def test_app_does_not_compress_a_precompressed_file_again(
    app_client: TestClient, dist: Path
) -> None:
    """The middleware leaves a response that already has a content encoding alone."""
    (dist / "big.js").write_text(_BIG_JS)
    (dist / "big.js.br").write_bytes(brotli.compress(_BROTLI_TEXT.encode()))

    resp = app_client.get("/big.js", headers={"Accept-Encoding": "br, gzip"})

    assert resp.headers["content-encoding"] == "br"
    assert resp.text == _BROTLI_TEXT


@pytest.mark.parametrize("etag", ['W/"abc123"', '"abc123"'], ids=["weak", "strong"])
def test_app_compresses_api_json_and_keeps_its_etag(
    app_client: TestClient, etag: str
) -> None:
    """JSON over the size threshold is compressed; its ETag is left as the app set it.

    The frontend sends the ETag back as `If-Match`, so a compressor that rewrote it,
    strong or weak, would make every save after a compressed read fail (see
    DECISIONS.md, weak ETags).
    """
    big = {"items": ["menagerist"] * 200}

    async def endpoint(_: object) -> JSONResponse:
        return JSONResponse(big, headers={"ETag": etag})

    # Ahead of the SPA mount, which would otherwise answer first.
    app_client.app.router.routes.insert(0, Route("/api/v1/_big", endpoint))  # type: ignore[attr-defined]

    resp = app_client.get("/api/v1/_big", headers={"Accept-Encoding": "gzip"})

    assert resp.headers["content-encoding"] == "gzip"
    assert resp.headers["etag"] == etag
    assert resp.json() == big

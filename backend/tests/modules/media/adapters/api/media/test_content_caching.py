import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from starlette.requests import Request

from app.entrypoints.api.shared.http_headers import http_date
from app.modules.media.adapters.api.media.content_caching import (
    check_content_not_modified,
    content_cache_headers,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus


def _dummy_asset(created_at: datetime | None = None) -> MediaAsset:
    dt = created_at or datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    return MediaAsset(
        id=uuid.uuid4(),
        filename="test.jpg",
        content_type="image/jpeg",
        size=1024,
        sha256="abcdef1234567890",
        status=MediaStatus.ATTACHED,
        created_at=dt,
        updated_at=dt,
    )


def test_content_cache_headers() -> None:
    """content_cache_headers produces immutable ETag and Last-Modified headers."""
    asset = _dummy_asset()
    headers = content_cache_headers(asset)
    assert headers["ETag"] == '"abcdef1234567890"'
    assert headers["Cache-Control"] == "private, max-age=31536000, immutable"
    assert headers["Last-Modified"] == http_date(asset.created_at)


def test_check_content_not_modified_if_none_match() -> None:
    """check_content_not_modified returns 304 on matching or wildcard If-None-Match."""
    asset = _dummy_asset()

    # Exact ETag match
    req = MagicMock(spec=Request)
    req.headers = {"If-None-Match": '"abcdef1234567890"'}
    res = check_content_not_modified(req, asset)
    assert res is not None
    assert res.status_code == 304

    # Wildcard ETag match
    req.headers = {"If-None-Match": "*"}
    res = check_content_not_modified(req, asset)
    assert res is not None
    assert res.status_code == 304

    # ETag mismatch
    req.headers = {"If-None-Match": '"otherhash"'}
    assert check_content_not_modified(req, asset) is None


def test_check_content_not_modified_if_modified_since() -> None:
    """check_content_not_modified evaluates If-Modified-Since at second resolution."""
    dt = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    asset = _dummy_asset(created_at=dt)

    req = MagicMock(spec=Request)
    # Modified since is exact same second -> not modified
    req.headers = {"If-Modified-Since": http_date(dt)}
    res = check_content_not_modified(req, asset)
    assert res is not None
    assert res.status_code == 304

    # Modified since is earlier -> modified (None)
    earlier = datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC)
    req.headers = {"If-Modified-Since": http_date(earlier)}
    assert check_content_not_modified(req, asset) is None

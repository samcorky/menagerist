from datetime import UTC, datetime
from typing import TYPE_CHECKING

from starlette.responses import Response

from app.entrypoints.api.shared.http_headers import http_date, parse_http_date

if TYPE_CHECKING:
    from starlette.requests import Request

    from app.modules.media.domain.media_asset import MediaAsset


def _cache_headers(*, etag_hash: str, last_modified: datetime) -> dict[str, str]:
    return {
        "ETag": f'"{etag_hash}"',
        "Last-Modified": http_date(last_modified),
        "Cache-Control": "private, max-age=31536000, immutable",
    }


def _check_not_modified(
    request: Request, *, etag_hash: str, last_modified: datetime
) -> Response | None:
    headers = _cache_headers(etag_hash=etag_hash, last_modified=last_modified)
    etag = headers["ETag"]

    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and (if_none_match == etag or if_none_match == "*"):
        return Response(status_code=304, headers=headers)

    if_modified_since = request.headers.get("If-Modified-Since")
    if if_modified_since:
        since = parse_http_date(if_modified_since)
        utc_modified = last_modified.astimezone(UTC)
        # Compare at second resolution. RFC 1123 omits sub-second precision.
        if since and utc_modified.replace(microsecond=0) <= since.astimezone(UTC):
            return Response(status_code=304, headers=headers)

    return None


def content_cache_headers(asset: MediaAsset) -> dict[str, str]:
    """Immutable cache headers for content addressed by ``sha256``.

    Deliberately keyed on ``sha256`` + ``created_at`` rather than the
    shared_kernel ``etag_from_entity()`` pattern (``id`` + ``updated_at``):
    every lifecycle transition (stage -> attach -> orphan) calls ``touch()``
    and bumps ``updated_at`` even though the underlying bytes never change,
    which would false-invalidate the cache on every move. The hash is stable
    across the entire lifecycle, so this is safe to cache as ``immutable``
    regardless of the asset's current status.

    Covers only the original file's bytes — see ``thumbnail_cache_headers``
    for the derived thumbnail, which is keyed on its own hash.
    """
    return _cache_headers(etag_hash=asset.sha256, last_modified=asset.created_at)


def check_content_not_modified(request: Request, asset: MediaAsset) -> Response | None:
    """Return a bare 304 if the client's cached copy of the original is still current.

    Deliberately does not use the ConditionalRequest/ETaggable machinery in
    shared/conditional_request.py: that writes headers onto the request-scoped
    injected `response` dependency, which only reaches the client when a route
    returns a plain model for FastAPI to serialize. stream_media_content (and
    stream_media_thumbnail) return their own StreamingResponse instead, which
    would silently discard anything written to the injected response — so the
    200-path headers are attached directly via content_cache_headers() at the
    call site, and this function only ever returns a bare Response for the
    304 branch.
    """
    return _check_not_modified(
        request, etag_hash=asset.sha256, last_modified=asset.created_at
    )


def thumbnail_cache_headers(asset: MediaAsset) -> dict[str, str]:
    """Immutable cache headers for a generated thumbnail, keyed on its own hash.

    A thumbnail's bytes can change independently of the original file it was
    derived from — ``RegenerateThumbnails`` re-encodes attached assets after
    a thumbnailing fix (EXIF orientation, encoder quality) without touching
    the original. Keying the thumbnail's ETag on the *original's* `sha256`
    (as content_cache_headers does) made a freshly regenerated thumbnail
    indistinguishable from the stale one it replaced, so under
    ``Cache-Control: immutable`` neither the browser cache nor a conditional
    304 would ever pick up the new bytes. `thumbnail_sha256` is the hash of
    the thumbnail's own bytes, so regenerating it changes the cache key.

    Falls back to `asset.sha256` for thumbnails generated before
    `thumbnail_sha256` existed (nullable, unbackfilled); they get their own
    key the next time they're regenerated.
    """
    return _cache_headers(
        etag_hash=asset.thumbnail_sha256 or asset.sha256,
        last_modified=asset.created_at,
    )


def check_thumbnail_not_modified(
    request: Request, asset: MediaAsset
) -> Response | None:
    """Return a bare 304 if the client's cached thumbnail is still current.

    See `thumbnail_cache_headers` for why this validates against
    `thumbnail_sha256` rather than the original's `sha256`.
    """
    return _check_not_modified(
        request,
        etag_hash=asset.thumbnail_sha256 or asset.sha256,
        last_modified=asset.created_at,
    )

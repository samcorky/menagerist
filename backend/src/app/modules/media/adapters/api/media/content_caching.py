from datetime import UTC
from typing import TYPE_CHECKING

from starlette.responses import Response

from app.entrypoints.api.shared.http_headers import http_date, parse_http_date

if TYPE_CHECKING:
    from starlette.requests import Request

    from app.modules.media.domain.media_asset import MediaAsset


def content_cache_headers(asset: MediaAsset) -> dict[str, str]:
    """Immutable cache headers for content addressed by ``sha256``.

    Deliberately keyed on ``sha256`` + ``created_at`` rather than the
    shared_kernel ``etag_from_entity()`` pattern (``id`` + ``updated_at``):
    every lifecycle transition (stage -> attach -> orphan) calls ``touch()``
    and bumps ``updated_at`` even though the underlying bytes never change,
    which would false-invalidate the cache on every move. The hash is stable
    across the entire lifecycle, so this is safe to cache as ``immutable``
    regardless of the asset's current status. Applies equally to the
    original content and to a generated thumbnail, since both are served
    under the same asset row and hash.
    """
    return {
        "ETag": f'"{asset.sha256}"',
        "Last-Modified": http_date(asset.created_at),
        "Cache-Control": "private, max-age=31536000, immutable",
    }


def check_content_not_modified(request: Request, asset: MediaAsset) -> Response | None:
    """Return a bare 304 if the client's cached copy is still current, else None.

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
    headers = content_cache_headers(asset)
    etag = headers["ETag"]

    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and (if_none_match == etag or if_none_match == "*"):
        return Response(status_code=304, headers=headers)

    if_modified_since = request.headers.get("If-Modified-Since")
    if if_modified_since:
        since = parse_http_date(if_modified_since)
        utc_created = asset.created_at.astimezone(UTC)
        # Compare at second resolution. RFC 1123 omits sub-second precision.
        if since and utc_created.replace(microsecond=0) <= since.astimezone(UTC):
            return Response(status_code=304, headers=headers)

    return None

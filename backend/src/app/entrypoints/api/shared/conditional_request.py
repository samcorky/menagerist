from datetime import UTC
from typing import Annotated

from fastapi import Depends
from starlette.requests import Request  # noqa: TC002 — FastAPI resolves this at runtime
from starlette.responses import Response

from app.shared_kernel.etag import ETaggable, etag_from_entity

from .http_headers import http_date, parse_http_date


class ConditionalRequest:
    """Handles conditional GET (304) and PATCH (412) via ETag / Last-Modified."""

    def __init__(self, request: Request, response: Response) -> None:
        self._req = request
        self._res = response

    def check_get(self, entity: ETaggable) -> Response | None:
        """Set ETag/Last-Modified on the outgoing response.

        Returns a 304 Response if the client's copy is current, else None.
        """
        etag = etag_from_entity(entity)
        last_mod = http_date(entity.updated_at)
        self._res.headers["ETag"] = etag
        self._res.headers["Last-Modified"] = last_mod
        self._res.headers["Cache-Control"] = "private, no-cache"

        if_none_match = self._req.headers.get("If-None-Match")
        if if_none_match and (if_none_match == etag or if_none_match == "*"):
            return Response(
                status_code=304, headers={"ETag": etag, "Last-Modified": last_mod}
            )

        if_modified_since = self._req.headers.get("If-Modified-Since")
        if if_modified_since:
            since = parse_http_date(if_modified_since)
            utc_updated = entity.updated_at.astimezone(UTC)
            # Compare at second resolution. RFC 1123 omits sub-second precision.
            if since and utc_updated.replace(microsecond=0) <= since.astimezone(UTC):
                return Response(
                    status_code=304,
                    headers={"ETag": etag, "Last-Modified": last_mod},
                )

        return None

    def check_patch(self, current: ETaggable) -> Response | None:
        """Return 412 if If-Match or If-Unmodified-Since fails, else None."""
        if_match = self._req.headers.get("If-Match")
        if_unmodified_since = self._req.headers.get("If-Unmodified-Since")
        if not if_match and not if_unmodified_since:
            return None

        etag = etag_from_entity(current)

        if if_match and if_match != "*" and if_match != etag:
            return Response(status_code=412, headers={"ETag": etag})

        if if_unmodified_since:
            since = parse_http_date(if_unmodified_since)
            utc_updated = current.updated_at.astimezone(UTC)
            # Compare at second resolution. RFC 1123 omits sub-second precision.
            if since and utc_updated.replace(microsecond=0) > since.astimezone(UTC):
                return Response(status_code=412, headers={"ETag": etag})

        return None

    def set_response_etag(self, entity: ETaggable) -> None:
        """Attach ETag/Last-Modified to the response after a successful mutation."""
        self._res.headers["ETag"] = etag_from_entity(entity)
        self._res.headers["Last-Modified"] = http_date(entity.updated_at)


def get_conditional_request(request: Request, response: Response) -> ConditionalRequest:
    """FastAPI dependency that provides a ConditionalRequest for the current request."""
    return ConditionalRequest(request, response)


# Convenience alias for Annotated injection
ConditionalRequestDep = Annotated[ConditionalRequest, Depends(get_conditional_request)]

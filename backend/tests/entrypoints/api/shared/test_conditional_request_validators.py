"""Unit tests for validator precedence in `ConditionalRequest`."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from starlette.requests import Request
from starlette.responses import Response

from app.entrypoints.api.shared.conditional_request import ConditionalRequest
from app.entrypoints.api.shared.http_headers import http_date
from app.shared_kernel.etag import etag_from_entity

_UPDATED = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


@dataclass
class _Entity:
    id: uuid.UUID
    updated_at: datetime


_ENTITY = _Entity(id=uuid.uuid7(), updated_at=_UPDATED)
_ETAG = etag_from_entity(_ENTITY)
_STALE_ETAG = etag_from_entity(_ENTITY, "other")
_LAST_MODIFIED = http_date(_UPDATED)


def _cond(**headers: str) -> ConditionalRequest:
    """Build a ConditionalRequest for a request carrying `headers`."""
    scope = {
        "type": "http",
        "method": "GET",
        "headers": [
            (k.replace("_", "-").lower().encode(), v.encode())
            for k, v in headers.items()
        ],
    }
    return ConditionalRequest(Request(scope), Response())


def test_get_if_none_match_match_is_304() -> None:
    """A matching If-None-Match yields 304 with the ETag."""
    result = _cond(If_None_Match=_ETAG).check_get(_ENTITY)

    assert result is not None
    assert result.status_code == 304
    assert result.headers["ETag"] == _ETAG


def test_get_if_none_match_mismatch_ignores_matching_if_modified_since() -> None:
    """A mismatching ETag decides alone: a matching If-Modified-Since is ignored."""
    result = _cond(
        If_None_Match=_STALE_ETAG, If_Modified_Since=_LAST_MODIFIED
    ).check_get(_ENTITY)

    assert result is None


def test_get_if_modified_since_alone_is_304_when_unchanged() -> None:
    """Without If-None-Match, an unchanged If-Modified-Since still gives 304."""
    result = _cond(If_Modified_Since=_LAST_MODIFIED).check_get(_ENTITY)

    assert result is not None
    assert result.status_code == 304


def test_get_if_modified_since_alone_is_200_when_older() -> None:
    """An older If-Modified-Since proceeds to a full response."""
    older = http_date(_UPDATED - timedelta(hours=1))

    assert _cond(If_Modified_Since=older).check_get(_ENTITY) is None


def test_patch_if_match_match_ignores_failing_if_unmodified_since() -> None:
    """A matching If-Match decides alone: If-Unmodified-Since is ignored."""
    older = http_date(_UPDATED - timedelta(hours=1))

    result = _cond(If_Match=_ETAG, If_Unmodified_Since=older).check_patch(_ENTITY)

    assert result is None


def test_patch_if_unmodified_since_alone_still_412_when_stale() -> None:
    """Without If-Match, a failing If-Unmodified-Since is still a 412."""
    older = http_date(_UPDATED - timedelta(hours=1))

    result = _cond(If_Unmodified_Since=older).check_patch(_ENTITY)

    assert result is not None
    assert result.status_code == 412

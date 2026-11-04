"""Per-user request limits for the endpoints that are expensive to serve.

A route declares `dependencies=[Depends(rate_limited(RateLimitBucket.UPLOADS))]`.
The count lives in this process only, so with several workers the effective limit
is the setting times the number of workers; it protects the server's resources,
not accounts (credential guessing is throttled in the identity module, backed by
the database). The check runs after authentication, so a request that is not
signed in is a 401 and never uses a user's allowance.
"""

import math
import time
from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Any, assert_never

import structlog
from fastapi import Depends

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.problem_response import error_response
from app.platform.config.rate_limit import RateLimitSettings, get_rate_limit_settings
from app.shared_kernel.actor import Actor  # noqa: TC001
from app.shared_kernel.errors import TooManyRequestsError

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()

WINDOW_SECONDS = 60
# Counters for users who stopped calling are swept once the table is this large.
_MAX_ENTRIES = 10_000


class RateLimitBucket(StrEnum):
    """A group of routes that share one allowance."""

    UPLOADS = "uploads"
    THUMBNAILS = "thumbnails"
    SEARCH = "search"
    IMPORTS = "imports"


class RateLimitedError(TooManyRequestsError):
    """Raised when a caller has used a route group's allowance for now."""


def limit_for(settings: RateLimitSettings, bucket: RateLimitBucket) -> int:
    """Return how many requests `bucket` allows per window; `0` means no limit."""
    match bucket:
        case RateLimitBucket.UPLOADS:
            return settings.uploads_per_minute
        case RateLimitBucket.THUMBNAILS:
            return settings.thumbnails_per_minute
        case RateLimitBucket.SEARCH:
            return settings.search_per_minute
        case RateLimitBucket.IMPORTS:
            return settings.imports_per_minute
        case _:
            assert_never(bucket)


class FixedWindowCounter:
    """In-memory fixed-window request counts, per bucket and caller."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._windows: dict[tuple[RateLimitBucket, str], tuple[float, int]] = {}

    def hit(self, bucket: RateLimitBucket, caller: str, *, limit: int) -> int | None:
        """Count one request; return seconds to wait if it is over `limit`, else `None`.

        A refused request is not counted, so waiting out `Retry-After` always works.
        """
        now = self._clock()
        key = (bucket, caller)
        start, count = self._windows.get(key, (now, 0))
        if now - start >= WINDOW_SECONDS:
            start, count = now, 0
        if count >= limit:
            return max(1, math.ceil(start + WINDOW_SECONDS - now))
        self._windows[key] = (start, count + 1)
        if len(self._windows) > _MAX_ENTRIES:
            self._sweep(now)
        return None

    def _sweep(self, now: float) -> None:
        self._windows = {
            key: value
            for key, value in self._windows.items()
            if now - value[0] < WINDOW_SECONDS
        }


@lru_cache(maxsize=1)
def get_rate_limiter() -> FixedWindowCounter:
    """Return the process-wide counter."""
    return FixedWindowCounter()


def rate_limited(bucket: RateLimitBucket) -> Callable[..., None]:
    """Build a route dependency that enforces `bucket`'s allowance on the caller."""

    def enforce(
        actor: Annotated[Actor, Depends(get_current_actor)],
        counter: Annotated[FixedWindowCounter, Depends(get_rate_limiter)],
        settings: Annotated[RateLimitSettings, Depends(get_rate_limit_settings)],
    ) -> None:
        limit = limit_for(settings, bucket)
        if limit == 0:
            return
        retry_after = counter.hit(bucket, str(actor.id), limit=limit)
        if retry_after is not None:
            logger.warning("rate_limited", bucket=bucket, user_id=str(actor.id))
            raise RateLimitedError(
                "Too many requests. Try again later.", retry_after=retry_after
            )

    return enforce


def _rate_limited_response() -> dict[int | str, dict[str, Any]]:
    responses = error_response(
        RateLimitedError,
        detail="Too many requests. Try again later.",
        description="Too many requests recently; wait for `Retry-After` seconds.",
    )
    responses[429]["headers"] = {
        "Retry-After": {
            "description": "Seconds to wait before trying again.",
            "schema": {"type": "integer"},
        }
    }
    return responses


RATE_LIMITED_RESPONSE = _rate_limited_response()

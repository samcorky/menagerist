import uuid
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from app.entrypoints.api.shared.http.problem_response import register_exception_handlers
from app.entrypoints.api.shared.http.rate_limit import (
    WINDOW_SECONDS,
    FixedWindowCounter,
    RateLimitBucket,
    limit_for,
    rate_limited,
)
from app.platform.config.rate_limit import RateLimitSettings

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest


class Clock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        """Return the current time."""
        return self.now


def test_requests_up_to_the_limit_pass_and_the_next_waits_for_the_window() -> None:
    """The first `limit` pass; the next is told how long is left."""
    clock = Clock()
    counter = FixedWindowCounter(clock)
    for _ in range(3):
        assert counter.hit(RateLimitBucket.UPLOADS, "a", limit=3) is None

    clock.now += 20
    assert counter.hit(RateLimitBucket.UPLOADS, "a", limit=3) == WINDOW_SECONDS - 20


def test_a_refused_request_is_not_counted_and_a_new_window_starts_clean() -> None:
    """Waiting out the Retry-After always works."""
    clock = Clock()
    counter = FixedWindowCounter(clock)
    assert counter.hit(RateLimitBucket.SEARCH, "a", limit=1) is None
    for _ in range(5):
        assert counter.hit(RateLimitBucket.SEARCH, "a", limit=1) is not None

    clock.now += WINDOW_SECONDS
    assert counter.hit(RateLimitBucket.SEARCH, "a", limit=1) is None


def test_buckets_and_callers_are_counted_separately() -> None:
    """One caller's or group's use never spends another's."""
    counter = FixedWindowCounter(Clock())
    assert counter.hit(RateLimitBucket.UPLOADS, "a", limit=1) is None
    assert counter.hit(RateLimitBucket.UPLOADS, "b", limit=1) is None
    assert counter.hit(RateLimitBucket.IMPORTS, "a", limit=1) is None
    assert counter.hit(RateLimitBucket.UPLOADS, "a", limit=1) is not None


def test_stale_counters_are_swept_when_the_table_grows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Callers who stopped calling do not stay in memory."""
    monkeypatch.setattr("app.entrypoints.api.shared.http.rate_limit._MAX_ENTRIES", 2)
    clock = Clock()
    counter = FixedWindowCounter(clock)
    for caller in ("a", "b"):
        counter.hit(RateLimitBucket.UPLOADS, caller, limit=5)
    clock.now += WINDOW_SECONDS
    counter.hit(RateLimitBucket.UPLOADS, "c", limit=5)

    assert list(counter._windows) == [(RateLimitBucket.UPLOADS, "c")]


def test_every_bucket_has_a_limit_setting() -> None:
    """A new bucket without a setting fails here, not in production."""
    settings = RateLimitSettings()
    for bucket in RateLimitBucket:
        assert limit_for(settings, bucket) >= 0


def _app(bucket: RateLimitBucket) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/work", dependencies=[Depends(rate_limited(bucket))])
    async def work() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_a_route_over_its_limit_answers_429_with_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The global handler turns the refusal into a problem+json with Retry-After."""
    monkeypatch.setenv("MENAGERIST_RATE_LIMIT_UPLOADS_PER_MINUTE", "2")
    client = TestClient(_app(RateLimitBucket.UPLOADS))

    assert client.post("/work").status_code == 200
    assert client.post("/work").status_code == 200
    refused = client.post("/work")

    assert refused.status_code == 429
    assert refused.headers["content-type"].startswith("application/problem+json")
    assert 1 <= int(refused.headers["Retry-After"]) <= WINDOW_SECONDS


def test_zero_turns_the_limit_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """A limit of 0 never refuses."""
    monkeypatch.setenv("MENAGERIST_RATE_LIMIT_THUMBNAILS_PER_MINUTE", "0")
    client = TestClient(_app(RateLimitBucket.THUMBNAILS))

    assert all(client.post("/work").status_code == 200 for _ in range(50))


def test_each_user_has_their_own_allowance(
    monkeypatch: pytest.MonkeyPatch, as_user: Callable[..., None]
) -> None:
    """A second user is not refused because the first used up theirs."""
    monkeypatch.setenv("MENAGERIST_RATE_LIMIT_IMPORTS_PER_MINUTE", "1")
    app = _app(RateLimitBucket.IMPORTS)
    client = TestClient(app)
    assert client.post("/work").status_code == 200
    assert client.post("/work").status_code == 429

    as_user(app, uuid.uuid7())
    assert client.post("/work").status_code == 200

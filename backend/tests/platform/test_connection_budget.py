"""How many database connections the server could open, against what Postgres allows."""

import pytest

from app.platform.config import get_database_settings
from app.platform.config.server import MAX_WORKERS
from app.platform.connection_budget import (
    PER_PROCESS,
    RESERVED,
    connection_warning,
    fetch_max_connections,
    possible_connections,
    validate_workers,
)


def test_each_process_can_use_its_whole_pool() -> None:
    """A process may hold the pool plus overflow, so that is what is budgeted."""
    assert PER_PROCESS == 15


def test_counts_the_workers_and_the_background_worker() -> None:
    """The background worker process has its own pool beside the web workers."""
    assert possible_connections(workers=1) == 2 * PER_PROCESS
    assert possible_connections(workers=4) == 5 * PER_PROCESS


def test_no_warning_when_postgres_allows_enough() -> None:
    """The defaults (1 worker, 100 connections) fit with room to spare."""
    assert connection_warning(workers=1, max_connections=100) is None


def test_no_warning_exactly_at_the_limit() -> None:
    """Needing exactly what is available is fine."""
    need = possible_connections(workers=2)
    assert connection_warning(workers=2, max_connections=need + RESERVED) is None


def test_warns_one_past_the_limit_and_says_what_to_change() -> None:
    """One connection short is a warning naming both knobs and the numbers."""
    need = possible_connections(workers=2)
    message = connection_warning(workers=2, max_connections=need + RESERVED - 1)

    assert message is not None
    assert str(need) in message
    assert str(need + RESERVED - 1) in message
    assert "POSTGRES_MAX_CONNECTIONS" in message
    assert "MENAGERIST_SERVER_WORKERS" in message


def test_many_workers_against_the_default_limit_warns() -> None:
    """Eight workers need more than Postgres' default of 100."""
    assert connection_warning(workers=8, max_connections=100) is not None


@pytest.mark.parametrize("workers", [1, 4, MAX_WORKERS])
def test_accepts_a_sensible_worker_count(workers: int) -> None:
    """Counts from one up to the maximum are accepted unchanged."""
    assert validate_workers(workers) == workers


@pytest.mark.parametrize("workers", [0, -1, MAX_WORKERS + 1])
def test_rejects_a_worker_count_out_of_range(workers: int) -> None:
    """Zero, negative and absurd counts are refused with the allowed range."""
    with pytest.raises(ValueError, match=rf"1 and {MAX_WORKERS}"):
        validate_workers(workers)


@pytest.mark.integration
@pytest.mark.usefixtures("postgres_url")
async def test_reads_the_limit_from_a_real_postgres() -> None:
    """Asks the live server, so the answer is the number Postgres itself reports."""
    limit = await fetch_max_connections()

    assert limit is not None
    assert limit >= RESERVED


async def test_an_unreachable_database_gives_none_quickly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing listening is 'unknown', never an error that stops the server."""
    monkeypatch.setenv(
        "MENAGERIST_DATABASE_URL",
        "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/none",
    )
    get_database_settings.cache_clear()
    try:
        assert await fetch_max_connections() is None
    finally:
        get_database_settings.cache_clear()

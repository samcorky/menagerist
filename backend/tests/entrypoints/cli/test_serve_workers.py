"""`serve` takes a validated worker count and warns when the pools outgrow Postgres."""

from typing import TYPE_CHECKING

import pytest
import structlog

from app.entrypoints import cli
from app.platform import connection_budget
from app.platform.config import get_server_settings

if TYPE_CHECKING:
    from collections.abc import Iterator


class _FakeGranian:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def serve(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _fake_granian(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setattr("granian.Granian", _FakeGranian)
    get_server_settings.cache_clear()
    yield
    get_server_settings.cache_clear()


def _limit(monkeypatch: pytest.MonkeyPatch, value: int | None) -> None:
    async def fetch() -> int | None:
        return value

    monkeypatch.setattr(connection_budget, "fetch_max_connections", fetch)


def test_warns_when_the_pools_could_outgrow_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Eight workers against 100 connections warns, naming both settings."""
    _limit(monkeypatch, 100)

    with structlog.testing.capture_logs() as logs:
        cli.serve(workers=8)

    warnings = [log for log in logs if log["log_level"] == "warning"]
    assert len(warnings) == 1
    assert "POSTGRES_MAX_CONNECTIONS" in warnings[0]["event"]
    assert "MENAGERIST_SERVER_WORKERS" in warnings[0]["event"]


def test_stays_quiet_when_the_limit_is_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default single worker against 100 connections logs no warning."""
    _limit(monkeypatch, 100)

    with structlog.testing.capture_logs() as logs:
        cli.serve(workers=1)

    assert [log for log in logs if log["log_level"] == "warning"] == []


def test_starts_without_a_warning_when_the_limit_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable database is not a reason to refuse to start."""
    _limit(monkeypatch, None)

    with structlog.testing.capture_logs() as logs:
        cli.serve(workers=8)

    assert [log for log in logs if log["log_level"] == "warning"] == []


def test_workers_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """MENAGERIST_SERVER_WORKERS sets the count when the flag is not given."""
    seen: list[dict[str, object]] = []

    class Recording(_FakeGranian):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            seen.append(kwargs)

    monkeypatch.setattr("granian.Granian", Recording)
    monkeypatch.setenv("MENAGERIST_SERVER_WORKERS", "3")
    _limit(monkeypatch, 1000)

    cli.app(["serve"], exit_on_error=False)

    assert seen[0]["workers"] == 3


@pytest.mark.parametrize("value", ["0", "17", "four"])
def test_a_bad_worker_count_is_refused_with_the_range(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Out-of-range or non-numeric counts stop start-up with a clear message."""
    monkeypatch.setenv("MENAGERIST_SERVER_WORKERS", value)

    with pytest.raises(
        Exception, match=r"MENAGERIST_SERVER_WORKERS|between 1 and 16|workers"
    ):
        cli.app(["serve"], exit_on_error=False)


def _host(
    monkeypatch: pytest.MonkeyPatch, *, container: bool, cpus: int | None
) -> None:
    from app.platform import worker_count

    monkeypatch.setattr(worker_count, "in_container", lambda configured: container)
    monkeypatch.setattr(worker_count, "available_cpus", lambda: cpus)


def _serve_and_read_workers(monkeypatch: pytest.MonkeyPatch, call: object) -> object:
    seen: list[dict[str, object]] = []

    class Recording(_FakeGranian):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            seen.append(kwargs)

    monkeypatch.setattr("granian.Granian", Recording)
    _limit(monkeypatch, 1000)
    assert callable(call)
    call()
    return seen[0]["workers"]


def test_auto_runs_a_worker_per_core_on_a_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """`auto` outside a container follows the core count."""
    _host(monkeypatch, container=False, cpus=6)

    assert _serve_and_read_workers(monkeypatch, lambda: cli.serve(workers="auto")) == 6


def test_auto_runs_one_worker_in_a_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """`auto` inside a container is one, whatever the core count."""
    _host(monkeypatch, container=True, cpus=16)

    assert _serve_and_read_workers(monkeypatch, lambda: cli.serve(workers="auto")) == 1


def test_auto_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """MENAGERIST_SERVER_WORKERS=auto is understood, not rejected as a bad number."""
    _host(monkeypatch, container=False, cpus=4)
    monkeypatch.setenv("MENAGERIST_SERVER_WORKERS", "auto")

    assert (
        _serve_and_read_workers(
            monkeypatch, lambda: cli.app(["serve"], exit_on_error=False)
        )
        == 4
    )


def test_the_connection_warning_uses_the_resolved_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`auto` on a 16-core host is checked as 16 workers, not as the word."""
    _host(monkeypatch, container=False, cpus=16)
    _limit(monkeypatch, 100)

    with structlog.testing.capture_logs() as logs:
        cli.serve(workers="auto")

    assert [log for log in logs if log["log_level"] == "warning"] != []


def test_the_default_is_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing said, a host gets a worker per core."""
    _host(monkeypatch, container=False, cpus=5)

    assert _serve_and_read_workers(monkeypatch, lambda: cli.serve()) == 5


def test_reload_keeps_auto_at_one_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--reload` is for development, where one worker keeps restarts simple."""
    _host(monkeypatch, container=False, cpus=12)

    assert _serve_and_read_workers(monkeypatch, lambda: cli.serve(reload=True)) == 1


def test_reload_does_not_override_an_explicit_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit number is honoured even when reloading."""
    _host(monkeypatch, container=False, cpus=12)

    assert (
        _serve_and_read_workers(monkeypatch, lambda: cli.serve(reload=True, workers=3))
        == 3
    )

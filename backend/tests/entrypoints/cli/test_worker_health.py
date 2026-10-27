"""A container health probe checks the current worker process only."""

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
import time_machine

from app.entrypoints import cli
from app.entrypoints.cli import scheduling
from app.platform.config.scheduler import get_scheduler_settings

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 10, 27, tzinfo=UTC)


@pytest.mark.parametrize("healthy", [True, False])
def test_worker_health_command_reports_status_and_exit_code(
    healthy: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Docker receives zero for healthy and one for unhealthy, with readable output."""
    operation = AsyncMock(return_value=healthy)
    monkeypatch.setattr(cli, "check_worker_health_cli", operation)
    if healthy:
        cli.app(["worker-health"], result_action="return_value")
        assert "healthy" in capsys.readouterr().out
    else:
        with pytest.raises(SystemExit, match="1"):
            cli.app(["worker-health"], result_action="return_value")
        assert "unhealthy" in capsys.readouterr().err


def test_worker_health_output_stays_free_of_asyncio_debug_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Docker stores probe output, so debug logging must not add a line to it."""

    async def probe(*, identity_file: Path | None = None) -> bool:
        return True

    monkeypatch.setattr(cli, "check_worker_health_cli", probe)
    caplog.set_level(logging.DEBUG)
    cli.app(["worker-health"], result_action="return_value")
    assert not [record for record in caplog.records if record.name == "asyncio"]


@time_machine.travel(NOW, tick=False)
async def test_health_probe_uses_identity_timeout_and_closes_connections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The probe uses the application query, timeout and a short session."""
    identity = tmp_path / "worker-id"
    identity.write_text("this-worker", encoding="utf-8")
    factory = MagicMock()
    factory.return_value.__aenter__.return_value.scalar = AsyncMock(return_value=True)
    engine = MagicMock(dispose=AsyncMock())
    monkeypatch.setattr(scheduling, "get_session_factory", lambda: factory)
    monkeypatch.setattr(scheduling, "get_engine", lambda: engine)
    monkeypatch.setenv("MENAGERIST_WORKER_HEARTBEAT_TIMEOUT_SECONDS", "120")
    get_scheduler_settings.cache_clear()
    try:
        assert await scheduling.check_worker_health_cli(identity_file=identity)
    finally:
        get_scheduler_settings.cache_clear()
    statement = factory.return_value.__aenter__.return_value.scalar.call_args.args[0]
    values = statement.compile().params.values()
    assert "this-worker" in values
    assert NOW - timedelta(seconds=120) in values
    engine.dispose.assert_awaited_once()


@pytest.mark.parametrize("contents", [None, ""])
async def test_missing_or_empty_identity_fails_closed(
    tmp_path: Path,
    contents: str | None,
) -> None:
    """A probe cannot fall back to another process when its identity is unavailable."""
    identity = tmp_path / "worker-id"
    if contents is not None:
        identity.write_text(contents, encoding="utf-8")
    assert not await scheduling.check_worker_health_cli(identity_file=identity)


async def test_database_failure_is_unhealthy_and_disposes_connections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Database outages fail the probe without exposing connection details."""
    identity = tmp_path / "worker-id"
    identity.write_text("this-worker", encoding="utf-8")
    factory = MagicMock(side_effect=OSError("connection refused"))
    engine = MagicMock(dispose=AsyncMock())
    monkeypatch.setattr(scheduling, "get_session_factory", lambda: factory)
    monkeypatch.setattr(scheduling, "get_engine", lambda: engine)
    assert not await scheduling.check_worker_health_cli(identity_file=identity)
    engine.dispose.assert_awaited_once()


def test_worker_identity_replaces_old_process_and_cleans_up(tmp_path: Path) -> None:
    """Restarts use a fresh id; an exited process leaves no probe identity."""
    path = tmp_path / "worker-id"
    path.write_text("old-process", encoding="utf-8")
    with scheduling.worker_identity(path) as worker_id:
        assert worker_id != "old-process"
        assert path.read_text(encoding="utf-8") == worker_id
    assert not path.exists()


def test_identity_cleanup_preserves_a_replacement_process(tmp_path: Path) -> None:
    """An older process cannot remove a newer process's identity."""
    path = tmp_path / "worker-id"
    with scheduling.worker_identity(path):
        path.write_text("replacement", encoding="utf-8")
    assert path.read_text(encoding="utf-8") == "replacement"


def test_identity_cleanup_tolerates_a_missing_file(tmp_path: Path) -> None:
    """External removal during shutdown does not break cleanup."""
    path = tmp_path / "worker-id"
    with scheduling.worker_identity(path):
        path.unlink()


def test_worker_commands_accept_a_shared_identity_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple local workers can each use an explicit identity file."""
    path = tmp_path / "custom-id"
    running = AsyncMock()
    checking = AsyncMock(return_value=True)
    monkeypatch.setattr(cli, "run_worker_cli", running)
    monkeypatch.setattr(cli, "check_worker_health_cli", checking)
    cli.app(["worker", "--identity-file", str(path)], result_action="return_value")
    cli.app(
        ["worker-health", "--identity-file", str(path)], result_action="return_value"
    )
    running.assert_awaited_once_with(identity_file=path)
    checking.assert_awaited_once_with(identity_file=path)

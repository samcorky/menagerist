"""Thin job commands and worker startup preserve application boundaries."""

import asyncio
import json
import signal
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from app.entrypoints import cli
from app.entrypoints.cli import scheduling
from app.modules.scheduling.adapters.cli import job_app as commands
from app.modules.scheduling.application.list_jobs import JobStatus
from app.modules.scheduling.domain.job_run import JobRun
from app.shared_kernel.jobs import JobDefinition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


def test_job_commands_translate_operations_to_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cyclopts exposes metadata and synchronously returns the run operation result."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    listing = AsyncMock(
        return_value=[
            JobStatus(
                definition=JobDefinition(job_key="x"),
                expression=None,
                next_run_at=NOW,
                active_run=run,
            )
        ]
    )
    running = AsyncMock(return_value=run)
    monkeypatch.setattr(commands, "_list_jobs", listing)
    monkeypatch.setattr(commands, "_run_job", running)
    cli.app(["job", "list", "--json"], result_action="return_value")
    assert json.loads(capsys.readouterr().out) == [
        {
            "job_key": "x",
            "lane": "default",
            "schedule": None,
            "next_run_at": NOW.isoformat(),
            "active_run_id": str(run.id),
        }
    ]
    cli.app(["job", "run", "x", "--json"], result_action="return_value")
    assert json.loads(capsys.readouterr().out) == {
        "run_id": str(run.id),
        "job_key": "x",
        "status": "queued",
    }
    running.assert_awaited_once_with("x")


def test_worker_command_calls_async_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """The worker entrypoint is registered on the existing root CLI."""
    operation = AsyncMock()
    monkeypatch.setattr(cli, "run_worker_cli", operation)
    cli.app(["worker"], result_action="return_value")
    operation.assert_awaited_once_with()


async def test_schema_gate_waits_until_packaged_heads_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker retries schema mismatches and never runs migrations itself."""
    factory = AsyncMock()
    revisions = AsyncMock(side_effect=[(), ("old",), ("head",)])
    monkeypatch.setattr(scheduling, "db_current_revisions", revisions)
    monkeypatch.setattr(scheduling, "code_head_revisions", lambda: ("head",))
    assert await scheduling.wait_for_schema(
        factory, asyncio.Event(), retry_interval=0.001
    )
    assert revisions.await_count == 3


async def test_schema_gate_can_stop_during_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown interrupts retry waits while the database is unavailable."""
    stop = asyncio.Event()

    async def unavailable(factory: async_sessionmaker[AsyncSession]) -> tuple[str, ...]:
        stop.set()
        raise OSError("database unavailable")

    monkeypatch.setattr(scheduling, "db_current_revisions", unavailable)
    monkeypatch.setattr(scheduling, "code_head_revisions", lambda: ("head",))
    assert not await asyncio.wait_for(
        scheduling.wait_for_schema(AsyncMock(), stop), timeout=1
    )


async def test_signal_handlers_request_stop_and_restore_previous_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI shutdown uses portable signal handlers and restores them on exit."""
    from unittest.mock import Mock

    signals = Mock()
    monkeypatch.setattr(signal, "signal", signals)
    stop = asyncio.Event()
    with scheduling.stop_on_signals(stop):
        handler = signals.call_args_list[1].args[1]
        handler(signal.SIGTERM, None)
        await asyncio.sleep(0)
        assert stop.is_set()
    assert signals.call_count == 4


@pytest.mark.parametrize("ready", [False, True])
async def test_worker_entrypoint_waits_then_disposes_connections(
    monkeypatch: pytest.MonkeyPatch, ready: bool
) -> None:
    """The entrypoint only starts a worker after the schema gate succeeds."""
    from contextlib import nullcontext
    from unittest.mock import Mock

    engine = AsyncMock()
    worker = Mock(run=AsyncMock())
    build = Mock(return_value=worker)
    monkeypatch.setattr(scheduling, "get_engine", lambda: engine)
    monkeypatch.setattr(scheduling, "get_session_factory", Mock())
    monkeypatch.setattr(scheduling, "stop_on_signals", lambda stop: nullcontext())
    monkeypatch.setattr(scheduling, "wait_for_schema", AsyncMock(return_value=ready))
    monkeypatch.setattr(scheduling, "build_worker", build)
    await scheduling.run_worker_cli()
    assert worker.run.await_count == int(ready)
    engine.dispose.assert_awaited_once()
    assert build.call_count == int(ready)


async def test_job_entrypoints_dispose_connections_on_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CLI event loop closes only after its shared engine has been disposed."""
    from unittest.mock import Mock

    engine = AsyncMock()
    monkeypatch.setattr(scheduling, "get_engine", lambda: engine)
    monkeypatch.setattr(scheduling, "get_session_factory", Mock())
    monkeypatch.setattr(scheduling, "list_registered_jobs", AsyncMock(return_value=[]))
    assert await scheduling.list_jobs_cli() == []
    monkeypatch.setattr(
        scheduling, "run_registered_job", AsyncMock(side_effect=RuntimeError("failed"))
    )
    with pytest.raises(RuntimeError, match="failed"):
        await scheduling.run_job_cli("x")
    assert engine.dispose.await_count == 2


def test_job_commands_default_to_rich_tables(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Human-readable output follows the account-list command's Rich convention."""
    run = JobRun.create(job_key="backup.create", scheduled_for=NOW)
    monkeypatch.setattr(
        commands,
        "_list_jobs",
        AsyncMock(
            return_value=[
                JobStatus(
                    definition=JobDefinition(job_key="backup.create"),
                    expression="0 3 * * *",
                    next_run_at=NOW,
                    active_run=None,
                )
            ]
        ),
    )
    monkeypatch.setattr(commands, "_run_job", AsyncMock(return_value=run))
    cli.app(["job", "list"], result_action="return_value")
    output = capsys.readouterr().out
    assert "Job" in output
    assert "Lane" in output
    assert "backup.create" in output
    assert "0 3 * * *" in output
    cli.app(["job", "run", "backup.create"], result_action="return_value")
    output = capsys.readouterr().out
    assert "Job run" in output
    assert str(run.id) in output
    assert "queued" in output


def test_empty_job_catalogue_has_clear_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unwired catalogue explains its empty state and remains JSON-compatible."""
    monkeypatch.setattr(commands, "_list_jobs", AsyncMock(return_value=[]))
    cli.app(["job", "list"], result_action="return_value")
    assert "No jobs are registered" in capsys.readouterr().out
    cli.app(["job", "list", "--json"], result_action="return_value")
    assert json.loads(capsys.readouterr().out) == []


def test_job_errors_use_stderr_and_a_failing_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A use-case refusal is a readable CLI error rather than a traceback."""
    from app.modules.scheduling.domain.errors import UnknownJobError

    monkeypatch.setattr(
        commands, "_run_job", AsyncMock(side_effect=UnknownJobError("missing"))
    )
    with pytest.raises(SystemExit, match="1"):
        cli.app(["job", "run", "missing"])
    captured = capsys.readouterr()
    assert "missing" in captured.err
    assert captured.out == ""


def test_failed_job_reports_its_error_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cron callers can distinguish completed failure from successful invocation."""
    from app.modules.scheduling.domain.job_run import RunStatus

    run = JobRun.create(job_key="x", scheduled_for=NOW)
    run.status = RunStatus.FAILED
    run.error = "job failed"
    monkeypatch.setattr(commands, "_run_job", AsyncMock(return_value=run))
    with pytest.raises(SystemExit, match="1"):
        cli.app(["job", "run", "x", "--json"])
    assert json.loads(capsys.readouterr().out)["error"] == "job failed"


def test_json_output_stays_parseable_when_a_job_logs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Application logs belong on stderr while a command owns stdout."""
    import logging
    import sys

    handler = logging.StreamHandler(sys.stdout)
    root = logging.getLogger()
    root.addHandler(handler)

    async def operation(job_key: str) -> JobRun:
        logging.getLogger("test.job").warning("job diagnostic")
        return JobRun.create(job_key=job_key, scheduled_for=NOW)

    monkeypatch.setattr(commands, "_run_job", operation)
    try:
        cli.app(["job", "run", "x", "--json"], result_action="return_value")
        captured = capsys.readouterr()
        assert json.loads(captured.out)["job_key"] == "x"
        assert "job diagnostic" in captured.err
        assert handler.stream is sys.stdout
    finally:
        root.removeHandler(handler)

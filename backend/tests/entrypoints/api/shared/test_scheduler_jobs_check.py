"""Job-health diagnostics warn with one row per condition and never fail readiness."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import time_machine

from app.entrypoints.api.shared.bridges.scheduler_jobs_check import (
    ALL_KEYS,
    FAILING_KEY,
    OVERDUE_KEY,
    QUEUE_KEYS,
    STUCK_KEY,
    SchedulerJobsCheck,
)
from app.modules.scheduling.application.assess_job_health import (
    AssessJobHealth,
    JobHealth,
    LaneBacklog,
)
from app.modules.system.adapters.platform.readiness_check_registry import (
    ReadinessCheckRegistry,
)
from app.modules.system.domain.readiness import CheckStatus
from app.shared_kernel.jobs import Lane

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)


def _check(monkeypatch: pytest.MonkeyPatch, health: JobHealth) -> SchedulerJobsCheck:
    monkeypatch.setattr(AssessJobHealth, "handle", AsyncMock(return_value=health))
    return SchedulerJobsCheck(
        MagicMock(),
        registry=MagicMock(),
        schedules=MagicMock(),
        evaluator=MagicMock(),
    )


@time_machine.travel(NOW, tick=False)
async def test_healthy_jobs_pass_on_every_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """Five compact rows, all passing, with no output."""
    rows = await _check(monkeypatch, JobHealth()).run()
    assert tuple(rows) == ALL_KEYS
    assert all(row.status is CheckStatus.PASS for row in rows.values())
    assert all(row.output is None and row.observed_value == 0 for row in rows.values())
    assert all(row.time == NOW for row in rows.values())


async def test_each_condition_warns_on_its_own_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Names are listed in one sentence per row, never as a row per job."""
    health = JobHealth(
        overdue=("Backup", "Purge"),
        stuck=("Sync",),
        failing=("A", "B", "C"),
        backlogs=(
            LaneBacklog(
                lane=Lane.HEAVY,
                waiting=("Thumbnails",),
                oldest_wait=timedelta(hours=2, minutes=5),
                blocker="Backup",
            ),
        ),
    )
    rows = await _check(monkeypatch, health).run()
    assert (
        rows[OVERDUE_KEY].output
        == "Backup and Purge did not start at the scheduled time."
    )
    assert rows[STUCK_KEY].output == "Sync running for longer than expected."
    assert rows[FAILING_KEY].output == "A, B and C failed on recent runs."
    heavy = rows[QUEUE_KEYS[Lane.HEAVY]]
    assert heavy.status is CheckStatus.WARN
    assert heavy.output == "Thumbnails waiting 2 h 5 min, behind Backup."
    assert heavy.observed_value == 1
    assert rows[QUEUE_KEYS[Lane.DEFAULT]].status is CheckStatus.PASS
    assert rows[OVERDUE_KEY].observed_value == 2


@pytest.mark.parametrize(
    ("wait", "text"),
    [
        (timedelta(seconds=10), "1 min"),
        (timedelta(hours=3), "3 h"),
        (timedelta(minutes=42), "42 min"),
    ],
)
async def test_unattended_queue_says_nothing_is_running(
    monkeypatch: pytest.MonkeyPatch, wait: timedelta, text: str
) -> None:
    """With no blocker the lane has no consumer, which reads differently."""
    health = JobHealth(
        backlogs=(
            LaneBacklog(
                lane=Lane.DEFAULT, waiting=("X",), oldest_wait=wait, blocker=None
            ),
        )
    )
    row = (await _check(monkeypatch, health).run())[QUEUE_KEYS[Lane.DEFAULT]]
    assert row.output == f"X waiting {text}, and nothing is running in this queue."


async def test_check_failure_warns_on_every_row_without_leaking_details() -> None:
    """Diagnostics failures cannot fail readiness or disclose connection details."""
    check = SchedulerJobsCheck(
        MagicMock(side_effect=OSError("private connection details")),
        registry=MagicMock(),
        schedules=MagicMock(),
        evaluator=MagicMock(),
    )
    rows = await check.run()
    assert tuple(rows) == ALL_KEYS
    for row in rows.values():
        assert row.status is CheckStatus.WARN
        assert row.output == "Job health could not be checked."


async def test_database_outage_is_a_one_line_warning() -> None:
    """An unreachable database logs without a traceback."""
    import socket

    from structlog.testing import capture_logs

    check = SchedulerJobsCheck(
        MagicMock(side_effect=socket.gaierror(-2, "unknown host")),
        registry=MagicMock(),
        schedules=MagicMock(),
        evaluator=MagicMock(),
    )
    with capture_logs() as logs:
        await check.run()
    (entry,) = [e for e in logs if e["event"] == "job health check failed"]
    assert entry["log_level"] == "warning"
    assert "exc_info" not in entry


async def test_warnings_keep_readiness_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """A scheduler problem warns in the report and never fails readiness."""
    health = JobHealth(failing=("A",))
    report = await ReadinessCheckRegistry([_check(monkeypatch, health)]).check()
    assert report.status is CheckStatus.WARN

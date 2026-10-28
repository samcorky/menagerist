"""Thin Cyclopts adapters for registered jobs."""

import asyncio
import logging
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

from cyclopts import App
from rich.console import Console
from rich.text import Text

from app.modules.scheduling.domain.job_run import RunStatus
from app.platform.cli_output import Report
from app.shared_kernel.errors import DomainError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

    from app.modules.scheduling.application.list_jobs import JobStatus
    from app.modules.scheduling.domain.job_run import JobRun

job_app = App(
    name="job",
    help="Inspect and run registered background jobs.",
    console=Console(soft_wrap=True),
    error_console=Console(stderr=True, soft_wrap=True),
)


async def _unconfigured_list() -> list[JobStatus]:
    raise RuntimeError("Job operations have not been configured")


async def _unconfigured_run(job_key: str) -> JobRun:
    raise RuntimeError("Job operations have not been configured")


_list_jobs: Callable[[], Awaitable[list[JobStatus]]] = _unconfigured_list
_run_job: Callable[[str], Awaitable[JobRun]] = _unconfigured_run


def use_operations(
    list_jobs: Callable[[], Awaitable[list[JobStatus]]],
    run_job: Callable[[str], Awaitable[JobRun]],
) -> None:
    """Bind entrypoint-composed use-case operations without exposing repositories."""
    global _list_jobs, _run_job
    _list_jobs, _run_job = list_jobs, run_job


@job_app.command(name="list")
def list_jobs() -> Report:
    """List registered jobs, effective schedules and active runs."""
    rows = [
        {
            "job_key": status.definition.job_key,
            "lane": status.definition.lane.value,
            "schedule": status.expression,
            "next_run_at": status.next_run_at,
            "active_run_id": status.active_run.id if status.active_run else None,
        }
        for status in _run_operation(_list_jobs())
    ]
    return Report(value=rows, title="Jobs", empty="No jobs are registered.")


@job_app.command
def run(job_key: str) -> Report:
    """Run a registered job synchronously, reusing any existing active request.

    Args:
        job_key: Registered job to run.
    """
    result = _run_operation(_run_job(job_key))
    value: dict[str, object] = {
        "run_id": result.id,
        "job_key": result.job_key,
        "status": result.status.value,
    }
    if result.error is not None:
        value["error"] = result.error
    failed = result.status in {RunStatus.FAILED, RunStatus.ABANDONED}
    return Report(value=value, title="Job run", exit_code=1 if failed else 0)


def _run_operation[T](operation: Awaitable[T]) -> T:
    try:
        with _logs_to_stderr():
            return asyncio.run(operation)
    except DomainError as error:
        job_app.error_console.print(Text(str(error)), style="red")
        raise SystemExit(1) from error


@contextmanager
def _logs_to_stderr() -> Iterator[None]:
    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, logging.StreamHandler)
        and (handler.stream is sys.stdout or handler.stream is sys.__stdout__)
    ]
    streams = [handler.setStream(sys.stderr) for handler in handlers]
    try:
        yield
    finally:
        for handler, stream in zip(handlers, streams, strict=True):
            if stream is not None:
                handler.setStream(stream)

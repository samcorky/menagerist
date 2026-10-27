"""Thin Cyclopts adapters for registered jobs."""

import asyncio
import json
import logging
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Annotated

from cyclopts import App, Parameter
from rich.console import Console
from rich.table import Table
from rich.text import Text

from app.modules.scheduling.domain.job_run import RunStatus
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
def list_jobs(
    *, json_output: Annotated[bool, Parameter(name="--json", negative="")] = False
) -> None:
    """List registered jobs, effective schedules and active runs.

    Args:
        json_output: Print machine-readable JSON instead of a table.
    """
    statuses = _run_operation(_list_jobs())
    if json_output:
        _json(
            [
                {
                    "job_key": status.definition.job_key,
                    "lane": status.definition.lane.value,
                    "schedule": status.expression,
                    "next_run_at": status.next_run_at.isoformat()
                    if status.next_run_at
                    else None,
                    "active_run_id": str(status.active_run.id)
                    if status.active_run
                    else None,
                }
                for status in statuses
            ]
        )
        return
    if not statuses:
        job_app.console.print("No jobs are registered.")
        return
    table = Table("Job", "Lane", "Schedule", "Next run", "Active run", title="Jobs")
    for status in statuses:
        table.add_row(
            Text(status.definition.job_key),
            Text(status.definition.lane.value),
            Text(status.expression or "off"),
            Text(
                status.next_run_at.strftime("%Y-%m-%d %H:%M %Z")
                if status.next_run_at
                else "—"
            ),
            Text(
                f"{status.active_run.status.value} ({status.active_run.id})"
                if status.active_run
                else "—"
            ),
        )
    job_app.console.print(table)


@job_app.command
def run(
    job_key: str,
    *,
    json_output: Annotated[bool, Parameter(name="--json", negative="")] = False,
) -> None:
    """Run a registered job synchronously, reusing any existing active request.

    Args:
        job_key: Registered job to run.
        json_output: Print machine-readable JSON instead of a table.
    """
    result = _run_operation(_run_job(job_key))
    if json_output:
        payload = {
            "run_id": str(result.id),
            "job_key": result.job_key,
            "status": result.status.value,
        }
        if result.error is not None:
            payload["error"] = result.error
        _json(payload)
    else:
        table = Table("Field", "Value", title="Job run")
        table.add_row("Job", Text(result.job_key))
        table.add_row("Run ID", Text(str(result.id)))
        table.add_row("Status", Text(result.status.value))
        if result.error is not None:
            table.add_row("Reason", Text(result.error))
        job_app.console.print(table)
    if result.status in {RunStatus.FAILED, RunStatus.ABANDONED}:
        raise SystemExit(1)


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


def _json(value: object) -> None:
    job_app.console.print(
        json.dumps(value, indent=2), markup=False, highlight=False, soft_wrap=True
    )

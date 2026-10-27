"""Invoke registered handlers with guards and independent execution recording."""

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.modules.scheduling.application.check_job_execution import (
    CheckJobExecutionQuery,
)
from app.modules.scheduling.application.finish_job_run import FinishJobRunCommand
from app.modules.scheduling.application.get_job_next_run import GetJobNextRunQuery
from app.modules.scheduling.application.heartbeat_job_run import HeartbeatJobRunCommand
from app.modules.scheduling.domain.errors import LostClaimError, UnknownRunError
from app.modules.scheduling.domain.job_run import RunStatus
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from app.modules.scheduling.application.check_job_execution import CheckJobExecution
    from app.modules.scheduling.application.finish_job_run import FinishJobRun
    from app.modules.scheduling.application.get_job_next_run import GetJobNextRun
    from app.modules.scheduling.application.heartbeat_job_run import HeartbeatJobRun
    from app.modules.scheduling.domain.job_run import JobRun
    from app.modules.scheduling.ports.restore_guard import RestoreGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.jobs import JobDefinition

type JobHandler = Callable[[Actor], Awaitable[None]]

logger = structlog.get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _elapsed(started: float) -> float:
    return round(time.monotonic() - started, 3)


class JobExecutor:
    """Own handler tasks and resource lifetimes at the worker boundary."""

    def __init__(
        self,
        heartbeat: Callable[[], HeartbeatJobRun],
        finish: Callable[[], FinishJobRun],
        eligibility: CheckJobExecution,
        restore: RestoreGuard,
        *,
        now: Callable[[], datetime] = _utc_now,
        heartbeat_interval: float = 30,
        next_run: Callable[[], GetJobNextRun] | None = None,
        timezone: str = "UTC",
    ) -> None:
        self._heartbeat_factory = heartbeat
        self._finish_factory = finish
        self._eligibility = eligibility
        self._restore = restore
        self._now = now
        self._heartbeat_interval = heartbeat_interval
        self._next_run = next_run
        self._timezone = timezone

    async def execute(
        self, run: JobRun, job: JobDefinition, handler: JobHandler
    ) -> None:
        """Execute owned work, leaving cancelled or lost work for the reaper."""
        if run.worker_id is None:
            raise LostClaimError("An unclaimed job cannot execute")
        worker_id = run.worker_id
        with structlog.contextvars.bound_contextvars(
            job_key=run.job_key,
            run_id=str(run.id),
            lane=job.lane.value,
            worker_id=worker_id,
        ):
            started = time.monotonic()
            logger.info("job started")
            try:
                status, error = await self._record(run.id, worker_id, job, handler)
            except asyncio.CancelledError:
                logger.warning("job cancelled", duration_seconds=_elapsed(started))
                raise
            except LostClaimError, UnknownRunError:
                logger.warning("job claim lost", duration_seconds=_elapsed(started))
                raise
            next_run_at = await self._next_run_at(job)
            if status is RunStatus.SKIPPED:
                logger.info(
                    "job skipped",
                    reason=error,
                    duration_seconds=_elapsed(started),
                    next_run_at=next_run_at,
                )
            else:
                log = logger.info if status is RunStatus.SUCCEEDED else logger.warning
                log(
                    "job finished",
                    status=status.value,
                    duration_seconds=_elapsed(started),
                    next_run_at=next_run_at,
                )

    async def _next_run_at(self, job: JobDefinition) -> str | None:
        """Describe the next fire without letting a lookup hide a recorded result."""
        if self._next_run is None:
            return None
        try:
            upcoming = await self._next_run().handle(
                GetJobNextRunQuery(
                    job_key=job.job_key, now=self._now(), timezone=self._timezone
                ),
                SYSTEM_ACTOR,
            )
        except Exception:
            logger.warning("next scheduled run could not be determined", exc_info=True)
            return None
        return upcoming.isoformat() if upcoming else None

    async def _record(
        self, run_id: UUID, worker_id: str, job: JobDefinition, handler: JobHandler
    ) -> tuple[RunStatus, str | None]:
        await self._heartbeat(run_id, worker_id)
        async with self._restore.try_hold() as acquired:
            reason = await self._eligibility.handle(
                CheckJobExecutionQuery(job=job, restore_available=acquired),
                SYSTEM_ACTOR,
            )
            if reason is not None:
                await self._finish(run_id, worker_id, RunStatus.SKIPPED, reason)
                return RunStatus.SKIPPED, reason
            status, error = await self._run_with_heartbeats(run_id, worker_id, handler)
            await self._finish(run_id, worker_id, status, error)
            return status, error

    async def _heartbeat(self, run_id: UUID, worker_id: str) -> None:
        await self._heartbeat_factory().handle(
            HeartbeatJobRunCommand(run_id=run_id, worker_id=worker_id, now=self._now()),
            SYSTEM_ACTOR,
        )

    async def _finish(
        self, run_id: UUID, worker_id: str, status: RunStatus, error: str | None
    ) -> None:
        await self._finish_factory().handle(
            FinishJobRunCommand(
                run_id=run_id,
                worker_id=worker_id,
                status=status,
                now=self._now(),
                error=error,
            ),
            SYSTEM_ACTOR,
        )

    async def _invoke(
        self, run_id: UUID, handler: JobHandler
    ) -> tuple[RunStatus, str | None]:
        try:
            await handler(SYSTEM_ACTOR)
        except Exception as exc:
            logger.exception("scheduled job failed", run_id=run_id)
            return RunStatus.FAILED, repr(exc)
        return RunStatus.SUCCEEDED, None

    async def _heartbeat_loop(self, run_id: UUID, worker_id: str) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            await self._heartbeat(run_id, worker_id)

    async def _run_with_heartbeats(
        self, run_id: UUID, worker_id: str, handler: JobHandler
    ) -> tuple[RunStatus, str | None]:
        execution = asyncio.create_task(self._invoke(run_id, handler))
        heartbeat = asyncio.create_task(self._heartbeat_loop(run_id, worker_id))
        try:
            done, _ = await asyncio.wait(
                {execution, heartbeat}, return_when=asyncio.FIRST_COMPLETED
            )
            if heartbeat in done:
                await heartbeat
            return await execution
        finally:
            execution.cancel()
            heartbeat.cancel()
            await asyncio.gather(execution, heartbeat, return_exceptions=True)

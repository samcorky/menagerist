"""Invoke registered handlers with guards and independent execution recording."""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.modules.scheduling.application.check_job_execution import (
    CheckJobExecutionQuery,
)
from app.modules.scheduling.application.finish_job_run import FinishJobRunCommand
from app.modules.scheduling.application.heartbeat_job_run import HeartbeatJobRunCommand
from app.modules.scheduling.domain.errors import LostClaimError
from app.modules.scheduling.domain.job_run import RunStatus
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from app.modules.scheduling.application.check_job_execution import CheckJobExecution
    from app.modules.scheduling.application.finish_job_run import FinishJobRun
    from app.modules.scheduling.application.heartbeat_job_run import HeartbeatJobRun
    from app.modules.scheduling.domain.job_run import JobRun
    from app.modules.scheduling.ports.restore_guard import RestoreGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.jobs import JobDefinition

type JobHandler = Callable[[Actor], Awaitable[None]]

logger = structlog.get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
    ) -> None:
        self._heartbeat_factory = heartbeat
        self._finish_factory = finish
        self._eligibility = eligibility
        self._restore = restore
        self._now = now
        self._heartbeat_interval = heartbeat_interval

    async def execute(
        self, run: JobRun, job: JobDefinition, handler: JobHandler
    ) -> None:
        """Execute owned work, leaving cancelled or lost work for the reaper."""
        if run.worker_id is None:
            raise LostClaimError("An unclaimed job cannot execute")
        worker_id = run.worker_id
        await self._heartbeat(run.id, worker_id)
        async with self._restore.try_hold() as acquired:
            reason = await self._eligibility.handle(
                CheckJobExecutionQuery(job=job, restore_available=acquired),
                SYSTEM_ACTOR,
            )
            if reason is not None:
                await self._finish(run.id, worker_id, RunStatus.SKIPPED, reason)
                return
            status, error = await self._run_with_heartbeats(run.id, worker_id, handler)
            await self._finish(run.id, worker_id, status, error)

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

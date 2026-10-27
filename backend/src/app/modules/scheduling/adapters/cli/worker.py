"""Tick schedules and consume independent lanes through application use cases."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from app.modules.scheduling.application.claim_job_run import ClaimJobRunCommand
from app.modules.scheduling.application.finish_job_run import FinishJobRunCommand
from app.modules.scheduling.application.maintain_worker import MaintainWorkerCommand
from app.modules.scheduling.application.tick_schedules import TickSchedulesCommand
from app.modules.scheduling.domain.errors import (
    LostClaimError,
    UnknownJobError,
    UnknownRunError,
)
from app.modules.scheduling.domain.job_run import RunStatus
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import Lane

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.scheduling.adapters.cli.catalogue import JobCatalogue
    from app.modules.scheduling.adapters.cli.execution import JobExecutor
    from app.modules.scheduling.application.claim_job_run import ClaimJobRun
    from app.modules.scheduling.application.finish_job_run import FinishJobRun
    from app.modules.scheduling.application.maintain_worker import MaintainWorker
    from app.modules.scheduling.application.tick_schedules import TickSchedules

logger = structlog.get_logger(__name__)
DEFAULT_ABANDON_AFTER = timedelta(minutes=5)


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def wait_or_stop(stop: asyncio.Event, seconds: float) -> None:
    """Make polling and tick waits interruptible by shutdown."""
    with suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)


class Worker:
    """Give each lane one execution slot while ticking independently."""

    def __init__(
        self,
        catalogue: JobCatalogue,
        claim: Callable[[], ClaimJobRun],
        maintain: Callable[[], MaintainWorker],
        tick: Callable[[], TickSchedules],
        finish: Callable[[], FinishJobRun],
        executor: JobExecutor,
        *,
        worker_id: str,
        timezone: str,
        now: Callable[[], datetime] = _utc_now,
        tick_interval: float = 60,
        heartbeat_interval: float = 60,
        poll_interval: float = 1,
        shutdown_grace: float = 30,
        abandon_after: timedelta = DEFAULT_ABANDON_AFTER,
    ) -> None:
        self._catalogue = catalogue
        self._claim = claim
        self._maintain = maintain
        self._tick = tick
        self._finish = finish
        self._executor = executor
        self._worker_id = worker_id
        self._timezone = timezone
        self._now = now
        self._tick_interval = tick_interval
        self._heartbeat_interval = heartbeat_interval
        self._poll_interval = poll_interval
        self._shutdown_grace = shutdown_grace
        self._abandon_after = abandon_after

    async def run(self, stop: asyncio.Event) -> None:
        """Stop new claims on shutdown and bound the remaining execution time."""
        tasks = [
            asyncio.create_task(self._heartbeat(stop)),
            asyncio.create_task(self._maintenance(stop)),
        ]
        tasks.extend(asyncio.create_task(self._consume(lane, stop)) for lane in Lane)
        stopping = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait(
                [*tasks, stopping], return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                await task
            deadline = asyncio.timeout(self._shutdown_grace)
            try:
                async with deadline:
                    await asyncio.gather(*tasks)
            except TimeoutError:
                if not deadline.expired():
                    raise
                logger.warning(
                    "worker shutdown grace expired", worker_id=self._worker_id
                )
        finally:
            stopping.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(stopping, *tasks, return_exceptions=True)

    async def _heartbeat(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            now = self._now()
            await self._maintain().handle(
                MaintainWorkerCommand(
                    worker_id=self._worker_id,
                    now=now,
                    older_than=now - self._abandon_after,
                ),
                SYSTEM_ACTOR,
            )
            logger.debug("worker heartbeat recorded")
            await wait_or_stop(stop, self._heartbeat_interval)

    async def _maintenance(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            submitted = await self._tick().handle(
                TickSchedulesCommand(now=self._now(), timezone=self._timezone),
                SYSTEM_ACTOR,
            )
            for run in submitted:
                logger.info(
                    "scheduled run submitted",
                    job_key=run.job_key,
                    run_id=str(run.id),
                    scheduled_for=run.scheduled_for.isoformat(),
                    status=run.status.value,
                )
            logger.debug("schedule tick completed")
            await wait_or_stop(stop, self._tick_interval)

    async def _consume(self, lane: Lane, stop: asyncio.Event) -> None:
        while not stop.is_set():
            run = await self._claim().handle(
                ClaimJobRunCommand(
                    lanes=(lane,), worker_id=self._worker_id, now=self._now()
                ),
                SYSTEM_ACTOR,
            )
            if run is None:
                await wait_or_stop(stop, self._poll_interval)
                continue
            try:
                try:
                    handler = self._catalogue.handler_for(run.job_key)
                except UnknownJobError:
                    await self._finish().handle(
                        FinishJobRunCommand(
                            run_id=run.id,
                            worker_id=self._worker_id,
                            status=RunStatus.SKIPPED,
                            now=self._now(),
                            error="unknown_job",
                        ),
                        SYSTEM_ACTOR,
                    )
                    continue
                await self._executor.execute(
                    run, self._catalogue.registry.get(run.job_key), handler
                )
            except LostClaimError, UnknownRunError:
                logger.warning(
                    "worker execution claim lost",
                    run_id=run.id,
                    worker_id=self._worker_id,
                )

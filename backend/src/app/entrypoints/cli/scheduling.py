"""Compose scheduler execution through application use cases."""

import asyncio
import signal
import socket
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING
from uuid import uuid7

import structlog
from sqlalchemy.exc import SQLAlchemyError

from app.entrypoints.api.shared.settings_reader import get_settings_reader
from app.entrypoints.cli.backup_jobs import (
    LIVE_SCHEDULES,
    backup_job_bindings,
    backup_schedules,
)
from app.modules.identity.adapters.persistence.unit_of_work import build_identity_repos
from app.modules.identity.application.get_setup_status import (
    GetSetupStatus,
    GetSetupStatusQuery,
)
from app.modules.scheduling.adapters.cli.catalogue import JobCatalogue
from app.modules.scheduling.adapters.cli.execution import JobExecutor
from app.modules.scheduling.adapters.cli.jobs import prune_runs_job
from app.modules.scheduling.adapters.cli.worker import (
    DEFAULT_ABANDON_AFTER,
    Worker,
    wait_or_stop,
)
from app.modules.scheduling.adapters.persistence.job_run_reader import (
    SqlAlchemyJobRunReader,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_scheduling_uow,
)
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.adapters.platform.reader_schedule_source import (
    ReaderScheduleSource,
)
from app.modules.scheduling.adapters.platform.restore_guard import (
    SqlAlchemyRestoreGuard,
)
from app.modules.scheduling.application.check_job_execution import CheckJobExecution
from app.modules.scheduling.application.claim_job_run import (
    ClaimJobRun,
    ClaimJobRunCommand,
)
from app.modules.scheduling.application.finish_job_run import FinishJobRun
from app.modules.scheduling.application.get_job_next_run import GetJobNextRun
from app.modules.scheduling.application.get_job_run import GetJobRun, GetJobRunQuery
from app.modules.scheduling.application.get_worker_status import (
    GetWorkerStatus,
    GetWorkerStatusQuery,
)
from app.modules.scheduling.application.heartbeat_job_run import HeartbeatJobRun
from app.modules.scheduling.application.list_jobs import ListJobs, ListJobsQuery
from app.modules.scheduling.application.maintain_worker import (
    MaintainWorker,
    MaintainWorkerCommand,
)
from app.modules.scheduling.application.prune_job_runs import PruneJobRuns
from app.modules.scheduling.application.run_job_now import RunJobNow, RunJobNowCommand
from app.modules.scheduling.application.setting_keys import RUN_HISTORY_PER_JOB
from app.modules.scheduling.application.tick_schedules import TickSchedules
from app.modules.scheduling.domain.job_run import RunStatus
from app.platform.alembic_runner import code_head_revisions, db_current_revisions
from app.platform.config.scheduler import get_scheduler_settings
from app.platform.database import get_engine, get_session_factory
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager
    from types import FrameType

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.scheduling.application.list_jobs import JobStatus
    from app.modules.scheduling.domain.job_run import JobRun
    from app.modules.scheduling.ports.schedule_source import ScheduleSource
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.jobs import JobDefinition

logger = structlog.get_logger(__name__)


def default_worker_identity_file() -> Path:
    """Use the container's writable temporary filesystem for process identity."""
    return Path(gettempdir()) / "menagerist-worker-id"


def worker_log_context(worker_id: str) -> AbstractContextManager[None]:
    """Bind host and process identity to every log line emitted beneath it."""
    return structlog.contextvars.bound_contextvars(
        hostname=socket.gethostname(), worker_id=worker_id
    )


@contextmanager
def worker_identity(path: Path) -> Iterator[str]:
    """Publish a fresh process id and remove only this process's identity on exit."""
    worker_id = str(uuid7())
    path.write_text(worker_id, encoding="utf-8")
    try:
        yield worker_id
    finally:
        with suppress(FileNotFoundError):
            if path.read_text(encoding="utf-8") == worker_id:
                path.unlink()


async def check_worker_health_cli(*, identity_file: Path | None = None) -> bool:
    """Probe the local worker's heartbeat through the guarded application query."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    try:
        worker_id = (
            (identity_file or default_worker_identity_file())
            .read_text(encoding="utf-8")
            .strip()
        )
    except OSError, UnicodeError:
        return False
    if not worker_id:
        return False
    try:
        async with asyncio.timeout(5), get_session_factory()() as session:
            return await GetWorkerStatus(
                SqlAlchemyJobRunReader(session), get_access_guard()
            ).handle(
                GetWorkerStatusQuery(
                    since=datetime.now(UTC)
                    - timedelta(
                        seconds=get_scheduler_settings().worker_heartbeat_timeout_seconds
                    ),
                    worker_id=worker_id,
                ),
                SYSTEM_ACTOR,
            )
    except TimeoutError, SQLAlchemyError, OSError:
        logger.warning("worker health check failed")
        return False
    finally:
        await get_engine().dispose()


class SchedulingSetupState:
    """Bridge the scheduler's setup port to identity's existing status query."""

    def __init__(
        self, factory: async_sessionmaker[AsyncSession], guard: AccessGuard
    ) -> None:
        self._factory = factory
        self._guard = guard

    async def is_complete(self) -> bool:
        """Use a short read-only session for each eligibility check."""
        async with self._factory() as session:
            status = GetSetupStatus(build_identity_repos(session), self._guard)
            return not await status.handle(GetSetupStatusQuery(), SYSTEM_ACTOR)


def build_job_executor(
    factory: async_sessionmaker[AsyncSession],
    guard: AccessGuard,
    catalogue: JobCatalogue,
    source: ScheduleSource,
) -> JobExecutor:
    """Give each recording command its own transaction and a real access guard."""
    return JobExecutor(
        lambda: HeartbeatJobRun(create_scheduling_uow(factory), guard),
        lambda: FinishJobRun(create_scheduling_uow(factory), guard),
        CheckJobExecution(SchedulingSetupState(factory, guard), guard),
        SqlAlchemyRestoreGuard(factory),
        next_run=lambda: GetJobNextRun(
            catalogue.registry, source, CronScheduleEvaluator(), guard
        ),
        timezone=get_scheduler_settings().timezone.key,
    )


async def run_history_per_job() -> int:
    """The current quota of completed runs kept per job."""
    return await get_settings_reader().get(RUN_HISTORY_PER_JOB)


def build_catalogue() -> JobCatalogue:
    """Collect module job contributions at the composition root."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    return JobCatalogue(
        [
            prune_runs_job(
                lambda: PruneJobRuns(
                    create_scheduling_uow(get_session_factory()), get_access_guard()
                ),
                keep_per_job=run_history_per_job,
            ),
            *backup_job_bindings(),
        ]
    )


def build_schedule_source() -> ReaderScheduleSource:
    """Resolve editable schedules through the settings reader, the rest from env."""
    return ReaderScheduleSource(
        get_settings_reader(),
        live=LIVE_SCHEDULES,
        static={"scheduling.prune_schedule": "0 4 * * *", **backup_schedules()},
    )


def build_worker(
    factory: async_sessionmaker[AsyncSession],
    guard: AccessGuard,
    catalogue: JobCatalogue,
    source: ScheduleSource,
    *,
    worker_id: str | None = None,
) -> Worker:
    """Give each worker operation its own guarded application transaction."""
    return Worker(
        catalogue,
        lambda: ClaimJobRun(create_scheduling_uow(factory), guard),
        lambda: MaintainWorker(create_scheduling_uow(factory), guard),
        lambda: TickSchedules(
            create_scheduling_uow(factory),
            guard,
            catalogue.registry,
            source,
            CronScheduleEvaluator(),
        ),
        lambda: FinishJobRun(create_scheduling_uow(factory), guard),
        build_job_executor(factory, guard, catalogue, source),
        worker_id=worker_id if worker_id is not None else str(uuid7()),
        timezone=get_scheduler_settings().timezone.key,
        heartbeat_interval=get_scheduler_settings().worker_heartbeat_interval_seconds,
        transient_errors=(SQLAlchemyError, OSError),
    )


async def log_job_schedules(
    factory: async_sessionmaker[AsyncSession],
    guard: AccessGuard,
    catalogue: JobCatalogue,
    source: ScheduleSource,
) -> None:
    """Record each job's effective schedule once, so a worker's plan is visible."""
    for status in await list_registered_jobs(factory, guard, catalogue, source):
        logger.info(
            "job schedule",
            job_key=status.definition.job_key,
            lane=status.definition.lane.value,
            schedule=status.expression or "off",
            next_run_at=status.next_run_at.isoformat() if status.next_run_at else None,
        )


async def wait_for_schema(
    factory: async_sessionmaker[AsyncSession],
    stop: asyncio.Event,
    *,
    retry_interval: float = 5,
) -> bool:
    """Wait for the API's migration to reach the packaged head without migrating."""
    expected = set(code_head_revisions())
    while not stop.is_set():
        try:
            if set(await db_current_revisions(factory)) == expected:
                return True
            logger.warning("worker waiting for database migrations")
        except SQLAlchemyError, OSError:
            logger.warning("worker waiting for database connection")
        await wait_or_stop(stop, retry_interval)
    return False


@contextmanager
def stop_on_signals(stop: asyncio.Event) -> Iterator[None]:
    """Translate CLI termination signals into a cooperative worker stop request."""
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    previous = {item: signal.getsignal(item) for item in signals}

    def request_stop(signum: int, frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(stop.set)

    try:
        for item in signals:
            signal.signal(item, request_stop)
        yield
    finally:
        for item in signals:
            signal.signal(item, previous[item])


async def run_worker_cli(*, identity_file: Path | None = None) -> None:
    """Wait for schema readiness, run until termination and close pooled connections."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    stop = asyncio.Event()
    try:
        with (
            worker_identity(
                identity_file or default_worker_identity_file()
            ) as worker_id,
            stop_on_signals(stop),
            worker_log_context(worker_id),
        ):
            logger.info("worker starting")
            factory = get_session_factory()
            if await wait_for_schema(factory, stop):
                logger.info("worker started")
                guard, catalogue, source = (
                    get_access_guard(),
                    build_catalogue(),
                    build_schedule_source(),
                )
                await log_job_schedules(factory, guard, catalogue, source)
                await build_worker(
                    factory, guard, catalogue, source, worker_id=worker_id
                ).run(stop)
            logger.info("worker stopped")
    finally:
        await get_engine().dispose()


async def list_registered_jobs(
    factory: async_sessionmaker[AsyncSession],
    guard: AccessGuard,
    catalogue: JobCatalogue,
    source: ScheduleSource,
) -> list[JobStatus]:
    """Compose the existing read-only status query for a CLI operation."""
    async with factory() as session:
        query = ListJobs(
            SqlAlchemyJobRunReader(session),
            guard,
            catalogue.registry,
            source,
            CronScheduleEvaluator(),
        )
        return await query.handle(
            ListJobsQuery(
                now=datetime.now(UTC), timezone=get_scheduler_settings().timezone.key
            ),
            SYSTEM_ACTOR,
        )


async def run_registered_job(
    factory: async_sessionmaker[AsyncSession],
    guard: AccessGuard,
    catalogue: JobCatalogue,
    job_key: str,
    *,
    poll_interval: float = 1,
) -> JobRun:
    """Submit and target only the requested run, then use the shared executor."""
    job = catalogue.registry.get(job_key)
    submitted = await RunJobNow(
        create_scheduling_uow(factory), guard, catalogue.registry
    ).handle(RunJobNowCommand(job_key=job_key, now=datetime.now(UTC)), SYSTEM_ACTOR)
    worker_id = f"cli-{uuid7()}"
    with worker_log_context(worker_id):
        return await _drive_run(
            factory, guard, catalogue, job, submitted, worker_id, poll_interval
        )


async def _drive_run(
    factory: async_sessionmaker[AsyncSession],
    guard: AccessGuard,
    catalogue: JobCatalogue,
    job: JobDefinition,
    submitted: JobRun,
    worker_id: str,
    poll_interval: float,
) -> JobRun:
    while True:
        async with factory() as session:
            current = await GetJobRun(SqlAlchemyJobRunReader(session), guard).handle(
                GetJobRunQuery(run_id=submitted.id), SYSTEM_ACTOR
            )
        if current.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
            return current
        if current.status is RunStatus.QUEUED:
            claimed = await ClaimJobRun(create_scheduling_uow(factory), guard).handle(
                ClaimJobRunCommand(
                    lanes=(job.lane,),
                    worker_id=worker_id,
                    now=datetime.now(UTC),
                    run_id=submitted.id,
                ),
                SYSTEM_ACTOR,
            )
            if claimed is not None:
                await build_job_executor(
                    factory, guard, catalogue, build_schedule_source()
                ).execute(claimed, job, catalogue.handler_for(job.job_key))
                continue
        now = datetime.now(UTC)
        await MaintainWorker(create_scheduling_uow(factory), guard).handle(
            MaintainWorkerCommand(
                worker_id=worker_id, now=now, older_than=now - DEFAULT_ABANDON_AFTER
            ),
            SYSTEM_ACTOR,
        )
        await asyncio.sleep(poll_interval)


async def list_jobs_cli() -> list[JobStatus]:
    """List jobs and release the process-wide engine before its event loop closes."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    try:
        return await list_registered_jobs(
            get_session_factory(),
            get_access_guard(),
            build_catalogue(),
            build_schedule_source(),
        )
    finally:
        await get_engine().dispose()


async def run_job_cli(job_key: str) -> JobRun:
    """Run a job and release the process-wide engine on success or failure."""
    from app.entrypoints.api.shared.access_guard import get_access_guard

    try:
        return await run_registered_job(
            get_session_factory(), get_access_guard(), build_catalogue(), job_key
        )
    finally:
        await get_engine().dispose()

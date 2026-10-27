"""Scheduler composition queries setup and reserves the full CLI restore."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.cli import backups
from app.entrypoints.cli.scheduling import (
    SchedulingSetupState,
    build_job_executor,
    list_registered_jobs,
    run_registered_job,
)
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.application.restore_backup import RestoreBackup
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.domain.user import User
from app.modules.scheduling.adapters.cli.catalogue import JobBinding, JobCatalogue
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    build_scheduling_repos,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.platform.advisory_locks import BACKUP_RESTORE_LOCK_KEY
from app.platform.config.backup import BackupSettings
from app.shared_kernel.jobs import JobDefinition, Lane

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.backup.application.restore_backup import RestoreBackupCommand
    from app.shared_kernel.actor import Actor

pytestmark = pytest.mark.integration


async def test_health_cli_checks_only_its_own_process_heartbeat(
    postgres_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A healthy peer cannot mask this process's stale heartbeat in PostgreSQL."""
    from sqlalchemy import delete

    from app.entrypoints.cli import scheduling
    from app.modules.scheduling.adapters.persistence.models import WorkerHeartbeatModel
    from app.platform.config.scheduler import SchedulerSettings

    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(scheduling, "get_session_factory", lambda: factory)
    monkeypatch.setattr(scheduling, "get_engine", lambda: engine)
    monkeypatch.setattr(
        scheduling,
        "get_scheduler_settings",
        lambda: SchedulerSettings(
            worker_heartbeat_timeout_seconds=120,
            worker_heartbeat_interval_seconds=30,
        ),
    )
    identity = tmp_path / "worker-id"
    own_id, peer_id = str(uuid7()), str(uuid7())
    identity.write_text(own_id, encoding="utf-8")
    now = datetime.now(UTC)
    try:
        async with factory.begin() as session:
            recorder = build_scheduling_repos(session).recorder
            await recorder.worker_heartbeat(own_id, now - timedelta(minutes=3))
            await recorder.worker_heartbeat(peer_id, now)
        assert not await scheduling.check_worker_health_cli(identity_file=identity)
        async with factory.begin() as session:
            await build_scheduling_repos(session).recorder.worker_heartbeat(
                own_id,
                datetime.now(UTC),
            )
        assert await scheduling.check_worker_health_cli(identity_file=identity)
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(WorkerHeartbeatModel).where(
                    WorkerHeartbeatModel.worker_id.in_((own_id, peer_id))
                )
            )
        await engine.dispose()


async def test_registered_maintenance_prunes_through_the_real_executor(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production registration honours deployment retention and records its run."""
    from sqlalchemy import delete

    from app.entrypoints.cli import scheduling
    from app.modules.scheduling.adapters.persistence.models import JobRunModel
    from app.platform.config.scheduler import SchedulerSettings

    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(scheduling, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        scheduling,
        "get_scheduler_settings",
        lambda: SchedulerSettings(run_history_per_job=1),
    )
    key = f"retention-{uuid7()}"
    now = datetime.now(UTC)
    try:
        async with factory.begin() as session:
            repos = build_scheduling_repos(session)
            for _ in range(3):
                run = await repos.queue.enqueue(
                    JobRun.create(job_key=key, scheduled_for=now)
                )
                await repos.queue.claim([Lane.DEFAULT], "seed", now, run_id=run.id)
                await repos.recorder.finish(run.id, "seed", RunStatus.SUCCEEDED, now)
        catalogue = scheduling.build_catalogue()
        definition = catalogue.registry.get("scheduling.prune_runs")
        assert definition.schedule_key is not None
        assert (
            await scheduling.build_schedule_source().schedule_for(
                definition.schedule_key
            )
            == "0 4 * * *"
        )
        result = await run_registered_job(
            factory,
            get_access_guard(),
            catalogue,
            definition.job_key,
        )
        assert result.status is RunStatus.SUCCEEDED
        async with factory() as session:
            history = await build_scheduling_repos(session).reader.history(
                key, limit=10
            )
            assert [item.id for item in history] == [run.id]
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(JobRunModel).where(
                    JobRunModel.job_key.in_((key, "scheduling.prune_runs"))
                )
            )
        await engine.dispose()


async def test_production_worker_composition_executes_a_registered_job(
    postgres_url: str,
) -> None:
    """The production builder wires every worker command to independent sessions."""
    from sqlalchemy import delete

    from app.entrypoints.cli.scheduling import build_worker
    from app.modules.scheduling.adapters.persistence.models import (
        JobRunModel,
        WorkerHeartbeatModel,
    )

    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    key = f"test-{uuid7()}"
    stop = asyncio.Event()
    worker_ids: list[str] = []

    async def handler(actor: Actor) -> None:
        stop.set()

    catalogue = JobCatalogue(
        [
            JobBinding(
                definition=JobDefinition(
                    job_key=key, needs_setup_complete=False, lane=Lane.HEAVY
                ),
                handler=handler,
            )
        ]
    )
    try:
        async with factory.begin() as session:
            queued = await build_scheduling_repos(session).queue.enqueue(
                JobRun.create(
                    job_key=key, scheduled_for=datetime.now(UTC), lane=Lane.HEAVY
                )
            )
        await asyncio.wait_for(
            build_worker(
                factory, get_access_guard(), catalogue, InMemoryScheduleSource({})
            ).run(stop),
            timeout=5,
        )
        async with factory() as session:
            result = await build_scheduling_repos(session).reader.get(queued.id)
            assert result.status is RunStatus.SUCCEEDED
            assert result.worker_id is not None
            worker_ids.append(result.worker_id)
    finally:
        async with factory.begin() as session:
            await session.execute(delete(JobRunModel).where(JobRunModel.job_key == key))
            await session.execute(
                delete(WorkerHeartbeatModel).where(
                    WorkerHeartbeatModel.worker_id.in_(worker_ids)
                )
            )
        await engine.dispose()


async def test_synchronous_cli_retries_temporary_claim_contention(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A contended targeted claim cannot leave cron work queued after a success exit."""
    from sqlalchemy import delete

    from app.modules.scheduling.adapters.persistence.job_lock import lock_job
    from app.modules.scheduling.adapters.persistence.models import (
        JobRunModel,
        WorkerHeartbeatModel,
    )
    from app.modules.scheduling.application.claim_job_run import (
        ClaimJobRun,
        ClaimJobRunCommand,
    )

    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    key = f"test-{uuid7()}"
    attempts = 0
    called = False
    original = ClaimJobRun.handle

    async def handler(actor: Actor) -> None:
        nonlocal called
        called = True

    async def contended(
        self: ClaimJobRun, request: ClaimJobRunCommand, actor: Actor
    ) -> JobRun | None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            async with factory.begin() as session:
                await lock_job(session, key)
                return await original(self, request, actor)
        return await original(self, request, actor)

    monkeypatch.setattr(ClaimJobRun, "handle", contended)
    catalogue = JobCatalogue(
        [
            JobBinding(
                definition=JobDefinition(job_key=key, needs_setup_complete=False),
                handler=handler,
            )
        ]
    )
    try:
        result = await run_registered_job(
            factory,
            get_access_guard(),
            catalogue,
            key,
            poll_interval=0.001,
        )
        assert attempts >= 2
        assert called
        assert result.status is RunStatus.SUCCEEDED
    finally:
        async with factory.begin() as session:
            ids = await session.scalars(
                select(JobRunModel.worker_id).where(JobRunModel.job_key == key)
            )
            await session.execute(
                delete(WorkerHeartbeatModel).where(
                    WorkerHeartbeatModel.worker_id.in_(list(ids))
                )
            )
            await session.execute(
                delete(WorkerHeartbeatModel).where(
                    WorkerHeartbeatModel.worker_id.like("cli-%")
                )
            )
            await session.execute(delete(JobRunModel).where(JobRunModel.job_key == key))
        await engine.dispose()


@pytest.mark.parametrize("already_running", [False, True])
async def test_synchronous_job_targets_only_its_requested_run(
    postgres_url: str, already_running: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI execution never steals an unrelated queued job or an existing claim."""
    from sqlalchemy import delete

    from app.modules.scheduling.adapters.persistence.models import (
        JobRunModel,
        WorkerHeartbeatModel,
    )

    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    key = f"test-{uuid7()}"
    other_key = f"test-{uuid7()}"
    called = False

    async def handler(actor: Actor) -> None:
        nonlocal called
        called = True

    catalogue = JobCatalogue(
        [
            JobBinding(
                definition=JobDefinition(
                    job_key=key, needs_setup_complete=False, schedule_key="custom"
                ),
                handler=handler,
            )
        ]
    )
    observed_running = asyncio.Event()
    completions: list[asyncio.Task[None]] = []
    from app.modules.scheduling.application.get_job_run import GetJobRun, GetJobRunQuery

    original_read = GetJobRun.handle

    async def observe(self: GetJobRun, query: GetJobRunQuery, actor: Actor) -> JobRun:
        result = await original_read(self, query, actor)
        if result.status is RunStatus.RUNNING:
            observed_running.set()
        return result

    monkeypatch.setattr(GetJobRun, "handle", observe)
    try:
        async with factory.begin() as session:
            repos = build_scheduling_repos(session)
            unrelated = await repos.queue.enqueue(
                JobRun.create(job_key=other_key, scheduled_for=datetime.now(UTC))
            )
            if already_running:
                queued = await repos.queue.enqueue(
                    JobRun.create(job_key=key, scheduled_for=datetime.now(UTC))
                )
                await repos.queue.claim(
                    [Lane.DEFAULT], key, datetime.now(UTC), run_id=queued.id
                )
        if already_running:

            async def complete_existing() -> None:
                await observed_running.wait()
                async with factory.begin() as session:
                    await build_scheduling_repos(session).recorder.finish(
                        queued.id, key, RunStatus.SUCCEEDED, datetime.now(UTC)
                    )

            completions.append(asyncio.create_task(complete_existing()))
        result = await asyncio.wait_for(
            run_registered_job(
                factory,
                get_access_guard(),
                catalogue,
                key,
                poll_interval=0.001,
            ),
            timeout=5,
        )
        await asyncio.gather(*completions)
        assert called is not already_running
        assert result.status is RunStatus.SUCCEEDED
        async with factory() as session:
            assert (
                await build_scheduling_repos(session).reader.get(unrelated.id)
            ).status is RunStatus.QUEUED
        statuses = await list_registered_jobs(
            factory,
            get_access_guard(),
            catalogue,
            InMemoryScheduleSource({"custom": "* * * * *"}),
        )
        assert len(statuses) == 1
        assert statuses[0].expression == "* * * * *"
        assert statuses[0].next_run_at is not None
    finally:
        for completion in completions:
            completion.cancel()
        await asyncio.gather(*completions, return_exceptions=True)
        async with factory.begin() as session:
            await session.execute(
                delete(JobRunModel).where(JobRunModel.job_key.in_([key, other_key]))
            )
            await session.execute(
                delete(WorkerHeartbeatModel).where(
                    WorkerHeartbeatModel.worker_id == key
                )
            )
            await session.execute(
                delete(WorkerHeartbeatModel).where(
                    WorkerHeartbeatModel.worker_id.like("cli-%")
                )
            )
        await engine.dispose()


async def test_setup_bridge_uses_existing_identity_query(
    db_session: AsyncSession,
) -> None:
    """Setup completion follows account existence, including disabled accounts."""
    factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    state = SchedulingSetupState(factory, get_access_guard())
    assert not await state.is_complete()
    user = User.create(
        username="worker-test",
        display_name="Worker Test",
        password_hash="test",
        now=datetime.now(UTC),
    )
    user.disabled = True
    await SqlAlchemyUserRepository(db_session).add(user)
    assert await state.is_complete()


async def test_composed_executor_uses_durable_application_commands(
    postgres_url: str,
) -> None:
    """Production composition persists execution through separate command sessions."""
    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    key = f"test-{uuid7()}"
    try:
        async with factory.begin() as session:
            repos = build_scheduling_repos(session)
            await repos.queue.enqueue(JobRun.create(job_key=key, scheduled_for=now))
            run = await repos.queue.claim([Lane.DEFAULT], key, now)
            assert run is not None

        async def handler(actor: Actor) -> None:
            assert actor.is_system

        await build_job_executor(factory, get_access_guard()).execute(
            run, JobDefinition(job_key=key, needs_setup_complete=False), handler
        )
        async with factory() as session:
            result = await build_scheduling_repos(session).reader.get(run.id)
            assert result.status is RunStatus.SUCCEEDED
            assert result.finished_at is not None
    finally:
        from sqlalchemy import delete

        from app.modules.scheduling.adapters.persistence.models import (
            JobRunModel,
            WorkerHeartbeatModel,
        )

        async with factory.begin() as session:
            await session.execute(delete(JobRunModel).where(JobRunModel.job_key == key))
            await session.execute(
                delete(WorkerHeartbeatModel).where(
                    WorkerHeartbeatModel.worker_id == key
                )
            )
        await engine.dispose()


@pytest.mark.parametrize("fail", [False, True])
async def test_cli_restore_holds_exclusive_lock_through_use_case(
    postgres_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    """The CLI holds the same lock as API restore, including exceptional exits."""
    engine = create_async_engine(postgres_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(backups, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        backups, "get_backup_settings", lambda: BackupSettings(backup_path=tmp_path)
    )

    @asynccontextmanager
    async def media() -> AsyncIterator[InMemoryMediaFiles]:
        yield InMemoryMediaFiles()

    invoked = False

    async def restore(
        self: RestoreBackup, command: RestoreBackupCommand, actor: Actor
    ) -> None:
        nonlocal invoked
        invoked = True
        assert command.setup_only
        async with factory.begin() as session:
            assert not await session.scalar(
                select(func.pg_try_advisory_xact_lock_shared(BACKUP_RESTORE_LOCK_KEY))
            )
        if fail:
            raise RuntimeError("restore failed")

    monkeypatch.setattr(backups, "media_files", media)
    monkeypatch.setattr(RestoreBackup, "handle", restore)
    try:
        if fail:
            with pytest.raises(RuntimeError, match="restore failed"):
                await backups.restore_backup(
                    uuid7(), replace=True, guard=get_access_guard()
                )
        else:
            await backups.restore_backup(
                uuid7(), replace=True, guard=get_access_guard()
            )
        assert invoked
        async with factory.begin() as session:
            assert await session.scalar(
                select(func.pg_try_advisory_xact_lock(BACKUP_RESTORE_LOCK_KEY))
            )
    finally:
        await engine.dispose()

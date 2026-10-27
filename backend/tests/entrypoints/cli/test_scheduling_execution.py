"""Scheduler composition queries setup and reserves the full CLI restore."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.cli import backups
from app.entrypoints.cli.scheduling import SchedulingSetupState, build_job_executor
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.application.restore_backup import RestoreBackup
from app.modules.identity.adapters.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from app.modules.identity.domain.user import User
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    build_scheduling_repos,
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

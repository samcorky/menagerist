"""Compose CLI backup infrastructure without starting the API lifespan."""

import asyncio
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.backup_operations import create_backup, media_files
from app.platform import alembic_runner
from app.platform.config.backup import get_backup_settings
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path
    from uuid import UUID

    from app.modules.backup.domain.backup import BackupSummary
    from app.shared_kernel.access_guard import AccessGuard


async def backup_before_upgrade(revision: str) -> None:
    """Back up existing schemas only when the requested upgrade has work."""
    factory = get_session_factory()
    current = await alembic_runner.db_current_revisions(factory)
    if not current or not await alembic_runner.pending(revision):
        return
    target = alembic_runner.target_revisions(revision)
    await create_backup(
        label="pre-migration",
        from_revision=",".join(sorted(current)),
        to_revision=",".join(sorted(target)),
    )


def upgrade_with_backup(revision: str = "head", *, backup: bool = True) -> None:
    """Fail before DDL if an enabled pre-migration backup cannot complete."""
    if backup and get_backup_settings().before_migrate:

        async def prepare() -> None:
            from app.platform.database import get_engine

            try:
                await backup_before_upgrade(revision)
            finally:
                await get_engine().dispose()

        asyncio.run(prepare())
    alembic_runner.upgrade(revision)


async def restore_backup(backup_id: UUID, *, replace: bool, guard: AccessGuard) -> None:
    """Select the setup gate when no accounts exist and run the restore."""
    from sqlalchemy import func, select

    from app.modules.backup.adapters.persistence.database_restorer import (
        SqlAlchemyDatabaseRestorer,
    )
    from app.modules.backup.adapters.storage.local_backup_store import (
        LocalDirectoryBackupStore,
    )
    from app.modules.backup.adapters.storage.local_backup_workspace import (
        LocalBackupWorkspace,
    )
    from app.modules.backup.application.restore_backup import (
        RestoreBackup,
        RestoreBackupCommand,
    )
    from app.modules.identity.adapters.persistence.unit_of_work import (
        build_identity_repos,
    )
    from app.modules.identity.application.get_setup_status import (
        GetSetupStatus,
        GetSetupStatusQuery,
    )
    from app.platform.advisory_locks import BACKUP_RESTORE_LOCK_KEY
    from app.shared_kernel.actor import SYSTEM_ACTOR

    factory = get_session_factory()
    async with factory() as lock_session, lock_session.begin():
        await lock_session.execute(
            select(func.pg_advisory_xact_lock(BACKUP_RESTORE_LOCK_KEY))
        )
        async with factory() as session:
            setup_only = await GetSetupStatus(
                build_identity_repos(session), guard
            ).handle(GetSetupStatusQuery(), SYSTEM_ACTOR)
        settings = get_backup_settings()
        async with media_files() as media:
            await RestoreBackup(
                LocalDirectoryBackupStore(settings.path),
                SqlAlchemyDatabaseRestorer(factory),
                media,
                LocalBackupWorkspace(settings.path),
                guard,
            ).handle(
                RestoreBackupCommand(
                    backup_id=backup_id, replace=replace, setup_only=setup_only
                ),
                SYSTEM_ACTOR,
            )


async def export_user_data(user_id: UUID, output: Path) -> BackupSummary:
    """Export one explicit owner and stream their archive to a local file."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.modules.backup.adapters.persistence.user_database_snapshot import (
        SqlAlchemyUserDatabaseSnapshot,
    )
    from app.modules.backup.adapters.storage.local_backup_store import (
        LocalDirectoryBackupStore,
    )
    from app.modules.backup.application.export_user_data import (
        ExportUserData,
        ExportUserDataCommand,
    )
    from app.platform.app_info import load_app_info
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

    actor = Actor(id=user_id, roles=frozenset({"member"}))
    store = LocalDirectoryBackupStore(
        get_backup_settings().path / "users" / str(user_id)
    )
    async with media_files(scope=ContentFilter.of(user_id)) as media:
        summary = await ExportUserData(
            store,
            SqlAlchemyUserDatabaseSnapshot(get_session_factory()),
            media,
            get_access_guard(),
            app_version=load_app_info().version,
        ).handle(ExportUserDataCommand(), actor)
        with output.open("xb") as destination:
            async for chunk in store.read_bytes(summary.id):
                destination.write(chunk)
        return summary


async def import_user_data(user_id: UUID, archive: Path) -> None:
    """Verify a user archive in the owner's namespace before importing it."""
    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.entrypoints.api.shared.bridges.backup_user_validator import (
        BackupUserImportValidator,
    )
    from app.modules.backup.adapters.persistence.user_database_restorer import (
        SqlAlchemyUserDatabaseRestorer,
    )
    from app.modules.backup.adapters.storage.local_backup_store import (
        LocalDirectoryBackupStore,
    )
    from app.modules.backup.adapters.storage.local_backup_workspace import (
        LocalBackupWorkspace,
    )
    from app.modules.backup.application.import_user_data import (
        ImportUserData,
        ImportUserDataCommand,
    )
    from app.modules.backup.application.upload_backup import upload_verified_backup
    from app.modules.backup.domain.backup import BackupScope
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

    async def chunks() -> AsyncIterator[bytes]:
        with archive.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                yield chunk

    settings = get_backup_settings()
    path = settings.path / "users" / str(user_id)
    store = LocalDirectoryBackupStore(path)
    workspace = LocalBackupWorkspace(path)
    summary = await upload_verified_backup(
        store,
        workspace,
        chunks(),
        settings.max_upload_size,
        allowed_scope=BackupScope.USER,
    )
    actor = Actor(id=user_id, roles=frozenset({"member"}))
    async with media_files(scope=ContentFilter.of(user_id)) as media:
        await ImportUserData(
            store,
            SqlAlchemyUserDatabaseRestorer(
                get_session_factory(), BackupUserImportValidator()
            ),
            media,
            workspace,
            get_access_guard(),
        ).handle(ImportUserDataCommand(backup_id=summary.id), actor)

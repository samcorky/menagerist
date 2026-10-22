"""Thin command adapters for instance backup operations."""

import asyncio
import json
import sys
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from cyclopts import App

from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.application.delete_backup import (
    DeleteBackup,
    DeleteBackupCommand,
)
from app.modules.backup.application.list_backups import ListBackups, ListBackupsQuery
from app.modules.backup.application.open_backup import OpenBackup, OpenBackupQuery
from app.modules.backup.application.prune_backups import (
    PruneBackups,
    PruneBackupsCommand,
)
from app.modules.backup.application.verify_backup import VerifyBackup, VerifyBackupQuery
from app.platform.config.backup import get_backup_settings
from app.shared_kernel.access import Requires
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import DomainError, ForbiddenError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Coroutine
    from typing import Any

    from app.modules.backup.domain.backup import BackupSummary
    from app.shared_kernel.access import Access
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

backup_app = App(name="backup", help="Manage verified instance backups.")


class _DenyAll:
    """Guard used until the composition root supplies the real one."""

    async def check(self, actor: Actor, access: Access) -> None:
        raise ForbiddenError("Authorisation is not wired for the CLI.")

    def scope_for(self, actor: Actor) -> ContentFilter:
        raise ForbiddenError("Authorisation is not wired for the CLI.")

    def assert_can_view(self, actor: Actor, owner_id: UUID | None) -> None:
        raise ForbiddenError("Authorisation is not wired for the CLI.")

    assert_can_modify = assert_can_delete = assert_can_view


_guard: AccessGuard = _DenyAll()


def use_access_guard(guard: AccessGuard) -> None:
    """Supply the composition root's access guard."""
    global _guard
    _guard = guard


async def _unwired_create(label: str) -> BackupSummary:
    raise ForbiddenError("Backup composition is not wired for the CLI.")


async def _unwired_restore(backup_id: UUID, replace: bool, guard: AccessGuard) -> None:
    raise ForbiddenError("Backup composition is not wired for the CLI.")


_create: Callable[[str], Coroutine[Any, Any, BackupSummary]] = _unwired_create
_restore: Callable[[UUID, bool, AccessGuard], Coroutine[Any, Any, None]] = (
    _unwired_restore
)


def use_operations(
    create_operation: Callable[[str], Coroutine[Any, Any, BackupSummary]],
    restore_operation: Callable[[UUID, bool, AccessGuard], Coroutine[Any, Any, None]],
) -> None:
    """Wire operations whose media bridge belongs to the composition root."""
    global _create, _restore
    _create, _restore = create_operation, restore_operation


def _store() -> LocalDirectoryBackupStore:
    return LocalDirectoryBackupStore(get_backup_settings().backup_path)


def _run[T](operation: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(operation)
    except DomainError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


def _print(value: object) -> None:
    print(json.dumps(value, default=str, indent=2))


@backup_app.command
def create(*, label: str = "manual") -> None:
    """Create and verify an instance backup."""
    from app.modules.backup.application.permissions import BackupPermission

    async def run() -> None:
        await _guard.check(SYSTEM_ACTOR, Requires(BackupPermission.CREATE))
        _print(asdict(await _create(label)))

    _run(run())


@backup_app.command(name="list")
def list_backups() -> None:
    """List committed archives, newest first."""
    _print(
        [
            asdict(item)
            for item in _run(
                ListBackups(_store(), _guard).handle(ListBackupsQuery(), SYSTEM_ACTOR)
            )
        ]
    )


@backup_app.command
def verify(backup_id: UUID) -> None:
    """Check every file and the archive checksum."""
    report = _run(
        VerifyBackup(_store(), _guard).handle(
            VerifyBackupQuery(backup_id=backup_id), SYSTEM_ACTOR
        )
    )
    _print(asdict(report))
    if report.findings:
        raise SystemExit(1)


@backup_app.command
def prune(
    *,
    keep_last: int | None = None,
    older_than_days: int | None = None,
    pre_migration_keep: int | None = None,
    dry_run: bool = False,
) -> None:
    """Apply retention while keeping ordinary and pre-migration groups separate."""
    settings = get_backup_settings()
    report = _run(
        PruneBackups(
            _store(),
            _guard,
            keep_last=settings.keep_last,
            pre_migration_keep=settings.pre_migration_keep,
            user_export_ttl_hours=settings.user_export_ttl_hours,
        ).handle(
            PruneBackupsCommand(
                keep_last=keep_last,
                older_than=None
                if older_than_days is None
                else timedelta(days=older_than_days),
                pre_migration_keep=pre_migration_keep,
                dry_run=dry_run,
            ),
            SYSTEM_ACTOR,
        )
    )
    _print(asdict(report))


@backup_app.command
def download(backup_id: UUID, output: Path) -> None:
    """Stream an archive to a new local file."""

    async def run() -> None:
        opened = await OpenBackup(_store(), _guard).handle(
            OpenBackupQuery(backup_id=backup_id), SYSTEM_ACTOR
        )
        with output.open("xb") as destination:
            async for chunk in opened.chunks:
                destination.write(chunk)

    _run(run())


@backup_app.command
def delete(backup_id: UUID) -> None:
    """Delete a committed archive."""
    _run(
        DeleteBackup(_store(), _guard).handle(
            DeleteBackupCommand(backup_id=backup_id), SYSTEM_ACTOR
        )
    )


@backup_app.command
def upload(archive: Path) -> None:
    """Verify and store an archive from a local file."""
    from app.modules.backup.adapters.storage.local_backup_workspace import (
        LocalBackupWorkspace,
    )
    from app.modules.backup.application.upload_backup import (
        UploadBackup,
        UploadBackupCommand,
    )

    async def chunks() -> AsyncIterator[bytes]:
        with archive.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                yield chunk

    settings = get_backup_settings()
    summary = _run(
        UploadBackup(
            _store(),
            LocalBackupWorkspace(settings.backup_path),
            _guard,
            max_upload_size=settings.max_upload_size,
        ).handle(UploadBackupCommand(stream=chunks()), SYSTEM_ACTOR)
    )
    _print(asdict(summary))


@backup_app.command
def restore(backup_id: UUID, *, replace: bool = False) -> None:
    """Restore an instance archive. Stop the server before replacing live data."""
    _run(_restore(backup_id, replace, _guard))


async def _unwired_export_user(user_id: UUID, output: Path) -> BackupSummary:
    raise ForbiddenError("User transfer composition is not wired for the CLI.")


async def _unwired_import_user(user_id: UUID, archive: Path) -> None:
    raise ForbiddenError("User transfer composition is not wired for the CLI.")


_export_user: Callable[[UUID, Path], Coroutine[Any, Any, BackupSummary]] = (
    _unwired_export_user
)
_import_user: Callable[[UUID, Path], Coroutine[Any, Any, None]] = _unwired_import_user


def use_user_operations(
    export_operation: Callable[[UUID, Path], Coroutine[Any, Any, BackupSummary]],
    import_operation: Callable[[UUID, Path], Coroutine[Any, Any, None]],
) -> None:
    """Wire owner-scoped user transfer infrastructure."""
    global _export_user, _import_user
    _export_user, _import_user = export_operation, import_operation


@backup_app.command
def export_user(output: Path, *, user: UUID) -> None:
    """Export the explicit account's content into a new local archive."""
    from app.modules.backup.application.permissions import BackupPermission

    async def run() -> None:
        await _guard.check(SYSTEM_ACTOR, Requires(BackupPermission.CREATE))
        _print(asdict(await _export_user(user, output)))

    _run(run())


@backup_app.command
def import_user(archive: Path, *, user: UUID) -> None:
    """Import a user archive into the explicit account on a fresh instance."""
    from app.modules.backup.application.permissions import BackupPermission

    async def run() -> None:
        await _guard.check(SYSTEM_ACTOR, Requires(BackupPermission.RESTORE))
        await _import_user(user, archive)

    _run(run())

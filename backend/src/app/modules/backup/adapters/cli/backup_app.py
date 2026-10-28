"""Thin command adapters for instance backup operations."""

import asyncio
import sys
from contextlib import nullcontext
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Annotated
from uuid import UUID  # noqa: TC003

from cyclopts import App, Parameter

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
from app.modules.backup.application.setting_keys import KEEP_LAST, USER_EXPORT_TTL_HOURS
from app.modules.backup.application.verify_backup import VerifyBackup, VerifyBackupQuery
from app.platform.cli_output import Report
from app.platform.cli_progress import activity, byte_progress, confirm
from app.platform.config.backup import get_backup_settings
from app.shared_kernel.access import Requires
from app.shared_kernel.access_guard import DenyAllAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import DomainError, ForbiddenError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Coroutine
    from typing import Any

    from app.modules.backup.domain.backup import BackupSummary
    from app.modules.backup.domain.verification import PruneReport
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.settings import SettingKey, SettingsReader

backup_app = App(name="backup", help="Manage verified instance backups.")


_guard: AccessGuard = DenyAllAccessGuard()


class _UnwiredSettings:
    async def get[T](self, key: SettingKey[T], *, user_id: UUID | None = None) -> T:
        raise ForbiddenError("Settings are not wired for the CLI.")


_settings: Callable[[], SettingsReader] = _UnwiredSettings


def use_settings_reader(reader: Callable[[], SettingsReader]) -> None:
    """Supply the composition root's settings reader, resolved when a command runs."""
    global _settings
    _settings = reader


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
    return LocalDirectoryBackupStore(get_backup_settings().path)


def _run[T](operation: Coroutine[Any, Any, T], working: str | None = None) -> T:
    try:
        with activity(working) if working else nullcontext():
            return asyncio.run(operation)
    except DomainError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


def _summary(message: str, summary: BackupSummary) -> dict[str, object]:
    return {"message": message, **asdict(summary)}


@backup_app.command
def create(*, label: str = "manual") -> dict[str, object]:
    """Create and verify an instance backup."""
    from app.modules.backup.application.permissions import BackupPermission

    async def run() -> BackupSummary:
        await _guard.check(SYSTEM_ACTOR, Requires(BackupPermission.CREATE))
        return await _create(label)

    return _summary(
        "Backup created and verified", _run(run(), "Creating and verifying the backup")
    )


@backup_app.command(name="list")
def list_backups() -> Report:
    """List committed archives, newest first."""
    backups = _run(
        ListBackups(_store(), _guard).handle(ListBackupsQuery(), SYSTEM_ACTOR)
    )
    return Report(
        value=[asdict(item) for item in backups],
        title="Backups",
        empty="No backups yet.",
    )


@backup_app.command
def verify(backup_id: UUID) -> Report:
    """Check every file and the archive checksum."""
    report = _run(
        VerifyBackup(_store(), _guard).handle(
            VerifyBackupQuery(backup_id=backup_id), SYSTEM_ACTOR
        ),
        "Checking every file",
    )
    message = "Backup is intact" if not report.findings else "Backup has problems"
    return Report(
        value={"message": message, "id": str(backup_id), **asdict(report)},
        exit_code=1 if report.findings else 0,
    )


@backup_app.command
def prune(
    *,
    keep_last: int | None = None,
    older_than_days: int | None = None,
    pre_migration_keep: int | None = None,
    dry_run: bool = False,
) -> Report:
    """Apply retention while keeping ordinary and pre-migration groups separate."""
    command = PruneBackupsCommand(
        keep_last=keep_last,
        older_than=None if older_than_days is None else timedelta(days=older_than_days),
        pre_migration_keep=pre_migration_keep,
        dry_run=dry_run,
    )

    async def apply() -> PruneReport:
        reader = _settings()
        return await PruneBackups(
            _store(),
            _guard,
            keep_last=await reader.get(KEEP_LAST),
            pre_migration_keep=get_backup_settings().pre_migration_keep,
            user_export_ttl_hours=await reader.get(USER_EXPORT_TTL_HOURS),
        ).handle(command, SYSTEM_ACTOR)

    report = _run(apply())
    message = "Dry run: nothing was deleted" if dry_run else "Retention applied"
    return Report(value={"message": message, **asdict(report)}, title="Retention")


@backup_app.command
def download(backup_id: UUID, output: Path) -> dict[str, object]:
    """Stream an archive to a new local file."""

    async def run() -> None:
        opened = await OpenBackup(_store(), _guard).handle(
            OpenBackupQuery(backup_id=backup_id), SYSTEM_ACTOR
        )
        with (
            byte_progress("Downloading", opened.summary.size) as advance,
            output.open("xb") as destination,
        ):
            async for chunk in opened.chunks:
                destination.write(chunk)
                advance(len(chunk))

    _run(run())
    return {
        "message": "Backup downloaded",
        "id": str(backup_id),
        "output": str(output),
        "size": output.stat().st_size,
    }


@backup_app.command
def delete(
    backup_id: UUID, *, yes: Annotated[bool, Parameter(name=["--yes", "-y"])] = False
) -> dict[str, object]:
    """Delete a committed archive.

    Args:
        backup_id: The archive to delete.
        yes: Do not ask for confirmation.
    """
    confirm(f"Permanently delete backup {backup_id}?", assume_yes=yes)
    _run(
        DeleteBackup(_store(), _guard).handle(
            DeleteBackupCommand(backup_id=backup_id), SYSTEM_ACTOR
        )
    )
    return {"message": "Backup deleted", "id": str(backup_id)}


@backup_app.command
def upload(archive: Path) -> dict[str, object]:
    """Verify and store an archive from a local file."""
    from app.modules.backup.adapters.storage.local_backup_workspace import (
        LocalBackupWorkspace,
    )
    from app.modules.backup.application.upload_backup import (
        UploadBackup,
        UploadBackupCommand,
    )

    async def chunks() -> AsyncIterator[bytes]:
        with (
            byte_progress("Uploading", archive.stat().st_size) as advance,
            archive.open("rb") as source,
        ):
            while chunk := source.read(1024 * 1024):
                yield chunk
                advance(len(chunk))

    settings = get_backup_settings()
    summary = _run(
        UploadBackup(
            _store(),
            LocalBackupWorkspace(settings.path),
            _guard,
            max_upload_size=settings.max_upload_size,
        ).handle(UploadBackupCommand(stream=chunks()), SYSTEM_ACTOR)
    )
    return _summary("Backup uploaded and verified", summary)


@backup_app.command
def restore(
    backup_id: UUID,
    *,
    replace: bool = False,
    yes: Annotated[bool, Parameter(name=["--yes", "-y"])] = False,
) -> dict[str, object]:
    """Restore an instance archive. Stop the server before replacing live data.

    Args:
        backup_id: The archive to restore.
        replace: Replace the data already on this instance.
        yes: Do not ask before replacing data.
    """
    if replace:
        confirm("Replace all data on this instance with the backup?", assume_yes=yes)
    _run(_restore(backup_id, replace, _guard), "Restoring the backup")
    return {
        "message": "Backup restored",
        "id": str(backup_id),
        "replaced_existing_data": replace,
    }


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
def export_user(output: Path, *, user: UUID) -> dict[str, object]:
    """Export the explicit account's content into a new local archive."""
    from app.modules.backup.application.permissions import BackupPermission

    async def run() -> BackupSummary:
        await _guard.check(SYSTEM_ACTOR, Requires(BackupPermission.CREATE))
        return await _export_user(user, output)

    summary = _run(run(), "Exporting the user's data")
    return {**_summary("User data exported", summary), "output": str(output)}


@backup_app.command
def import_user(archive: Path, *, user: UUID) -> dict[str, object]:
    """Import a user archive into the explicit account on a fresh instance."""
    from app.modules.backup.application.permissions import BackupPermission

    async def run() -> None:
        await _guard.check(SYSTEM_ACTOR, Requires(BackupPermission.RESTORE))
        await _import_user(user, archive)

    _run(run(), "Importing the user's data")
    return {"message": "User data imported", "user": str(user), "archive": str(archive)}

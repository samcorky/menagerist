from contextlib import aclosing
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

import structlog

from app.modules.backup.application.archive import parse_manifest
from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.application.verify_backup import _scan, verify_archive
from app.modules.backup.domain.backup import BackupManifest, BackupScope, MediaFileRef
from app.modules.backup.domain.errors import (
    CorruptBackupError,
    IncompatibleBackupError,
    RestoreTargetNotEmptyError,
)
from app.modules.backup.ports.archive_member import ArchiveMember
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase
from app.shared_kernel.progress import NULL_PROGRESS, Phase

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    from app.modules.backup.ports.backup_reader import BackupReader
    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_workspace import BackupWorkspace
    from app.modules.backup.ports.database_restorer import DatabaseRestorer
    from app.modules.backup.ports.media_files import MediaFiles
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.progress import ProgressReporter

type MediaUndo = list[tuple[MediaFileRef, UUID | None]]

logger = structlog.get_logger()

RESTORE_PLAN = (
    Phase(key="verify", label="Checking the backup", weight=2, unit="bytes"),
    Phase(key="database", label="Restoring your collection", weight=3),
    Phase(key="media", label="Restoring photos and files", weight=5),
)

# archive_manifest reads the archive twice (verify, then manifest metadata).
MANIFEST_PASSES = 2


@dataclass(frozen=True, kw_only=True)
class RestoreBackupCommand:
    """Restore a committed instance archive."""

    backup_id: UUID
    replace: bool = False
    setup_only: bool = False


async def start_verify_phase(
    store: BackupStore,
    backup_id: UUID,
    progress: ProgressReporter,
    *,
    passes: int = MANIFEST_PASSES,
) -> None:
    """Start the `verify` phase, sized as `passes` reads of the compressed archive."""
    await progress.start("verify", passes * await store.archive_size(backup_id))


async def archive_manifest(
    store: BackupStore, backup_id: UUID, progress: ProgressReporter = NULL_PROGRESS
) -> BackupManifest:
    """Verify all bytes before exposing the archive manifest.

    Reads the archive `MANIFEST_PASSES` times, advancing the running phase.
    """
    expected_digest = await store.archive_digest(backup_id)
    if (await verify_archive(store, backup_id, progress)).findings:
        raise CorruptBackupError("Backup failed integrity verification.")
    reader = await store.open(backup_id)
    _, metadata, _ = await _scan(reader, progress)
    if await reader.archive_digest() != expected_digest:
        raise CorruptBackupError("The backup changed after integrity verification.")
    return parse_manifest(metadata["manifest.json"])


async def _counting_rows(
    chunks: AsyncIterator[bytes], progress: ProgressReporter
) -> AsyncIterator[bytes]:
    """Pass chunks through, advancing `progress` by the rows each one holds."""
    async for chunk in chunks:
        yield chunk
        await progress.advance(chunk.count(b"\n"))


async def _write_media(
    ref: MediaFileRef,
    member: ArchiveMember,
    media: MediaFiles,
    workspace: BackupWorkspace,
    undo: MediaUndo,
) -> None:
    """Stage any file being replaced, then write the archived original."""
    # Stage only an original that will be replaced, so restoring into an
    # empty instance never writes to the backups directory.
    original = (
        await workspace.save(media.open(ref)) if await media.exists(ref) else None
    )
    undo.append((ref, original))
    await media.write(ref, member.chunks)


async def transactional_media_members(
    reader: BackupReader,
    manifest: BackupManifest,
    media: MediaFiles,
    workspace: BackupWorkspace,
    undo: MediaUndo,
    *,
    expected_digest: str | None = None,
    progress: ProgressReporter = NULL_PROGRESS,
) -> AsyncGenerator[ArchiveMember]:
    """Write media before the database consumer reaches its commit point.

    Reports the `database` phase in rows consumed and the `media` phase in files
    written; the caller owns the plan.
    """
    refs = {f"media/{ref.asset_id}": ref for ref in manifest.media}
    rows = sum(table.rows for table in manifest.tables)
    files = sum(
        1 for ref in manifest.media if ref.asset_id not in manifest.media_missing
    )
    phase = ""
    async with aclosing(reader.members()) as members:
        async for member in members:
            if member.name.startswith("data/"):
                if phase != "database":
                    phase = "database"
                    await progress.start("database", rows)
                yield ArchiveMember(
                    name=member.name, chunks=_counting_rows(member.chunks, progress)
                )
            elif member.name in refs:
                if phase != "media":
                    phase = "media"
                    await progress.start("media", files)
                await _write_media(refs[member.name], member, media, workspace, undo)
                await progress.advance()
            else:
                async for _ in member.chunks:
                    pass
    if expected_digest is not None and await reader.archive_digest() != expected_digest:
        raise CorruptBackupError("The backup changed after integrity verification.")


async def rollback_media(
    media: MediaFiles, workspace: BackupWorkspace, undo: MediaUndo
) -> None:
    """Restore overwritten originals as well as removing newly created files."""
    for ref, original in reversed(undo):
        if original is None:
            await media.remove(ref)
        else:
            await media.write(ref, workspace.read(original))


async def cleanup_media(workspace: BackupWorkspace, undo: MediaUndo) -> None:
    """Release staged undo copies after commit or rollback."""
    for _, original in undo:
        if original is not None:
            await workspace.remove(original)


async def restore_verified_backup(
    store: BackupStore,
    restorer: DatabaseRestorer,
    media: MediaFiles,
    workspace: BackupWorkspace,
    backup_id: UUID,
    *,
    replace: bool = False,
    setup_only: bool = False,
    progress: ProgressReporter = NULL_PROGRESS,
) -> None:
    """Verify and restore with reversible media writes inside the transaction.

    Reports against `RESTORE_PLAN` and ends the operation with `done()`. A failure
    propagates; whoever owns the reporter records it with `fail()`.
    """
    await progress.begin(RESTORE_PLAN)
    await start_verify_phase(store, backup_id, progress)
    expected_digest = await store.archive_digest(backup_id)
    manifest = await archive_manifest(store, backup_id, progress)
    if (
        manifest.scope != BackupScope.INSTANCE
        or manifest.format != "ndjson"
        or manifest.format_version != 1
    ):
        raise IncompatibleBackupError(
            "An instance archive in format version 1 is required."
        )
    if manifest.alembic_revision != await restorer.schema_revision():
        raise IncompatibleBackupError(
            "The backup migration revision differs from the target."
        )
    if not replace and not await restorer.is_empty():
        raise RestoreTargetNotEmptyError("The restore target is not empty.")
    undo: MediaUndo = []
    try:
        async with aclosing(
            transactional_media_members(
                await store.open(backup_id),
                manifest,
                media,
                workspace,
                undo,
                expected_digest=expected_digest,
                progress=progress,
            )
        ) as members:
            await restorer.restore_instance(
                members, replace=replace, setup_only=setup_only
            )
    except BaseException:
        await rollback_media(media, workspace, undo)
        raise
    finally:
        await cleanup_media(workspace, undo)
    await progress.done()


class RestoreBackup(UseCase[RestoreBackupCommand, None]):
    """Administrative instance restoration."""

    access: ClassVar[Access] = Requires(BackupPermission.RESTORE)

    def __init__(
        self,
        store: BackupStore,
        restorer: DatabaseRestorer,
        media: MediaFiles,
        workspace: BackupWorkspace,
        guard: AccessGuard,
        progress: ProgressReporter | None = None,
    ) -> None:
        self._guard = guard
        self._store, self._restorer, self._media, self._workspace = (
            store,
            restorer,
            media,
            workspace,
        )
        self._progress = progress or NULL_PROGRESS

    async def _handle(self, request: RestoreBackupCommand, actor: Actor) -> None:
        await restore_verified_backup(
            self._store,
            self._restorer,
            self._media,
            self._workspace,
            request.backup_id,
            replace=request.replace,
            setup_only=request.setup_only,
            progress=self._progress,
        )
        logger.warning(
            "instance backup restored",
            backup_id=request.backup_id,
            actor_id=actor.id,
            replace=request.replace,
        )

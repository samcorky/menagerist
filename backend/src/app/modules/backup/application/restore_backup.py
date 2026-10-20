from contextlib import aclosing
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from app.modules.backup.application.archive import parse_manifest
from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.application.verify_backup import _scan, verify_archive
from app.modules.backup.domain.backup import BackupManifest, BackupScope, MediaFileRef
from app.modules.backup.domain.errors import (
    CorruptBackupError,
    IncompatibleBackupError,
    MediaFileMissingError,
    RestoreTargetNotEmptyError,
)
from app.shared_kernel.cqrs import AuthorisedUseCase

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.modules.backup.ports.archive_member import ArchiveMember
    from app.modules.backup.ports.backup_reader import BackupReader
    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_workspace import BackupWorkspace
    from app.modules.backup.ports.database_restorer import DatabaseRestorer
    from app.modules.backup.ports.media_files import MediaFiles
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorization import AuthorizationPort

type MediaUndo = list[tuple[MediaFileRef, UUID | None]]

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class RestoreBackupCommand:
    """Restore a committed instance archive."""

    backup_id: UUID
    replace: bool = False
    setup_only: bool = False


async def archive_manifest(store: BackupStore, backup_id: UUID) -> BackupManifest:
    """Verify all bytes before exposing the archive manifest."""
    expected_digest = await store.archive_digest(backup_id)
    if (await verify_archive(store, backup_id)).findings:
        raise CorruptBackupError("Backup failed integrity verification.")
    reader = await store.open(backup_id)
    _, metadata, _ = await _scan(reader)
    if await reader.archive_digest() != expected_digest:
        raise CorruptBackupError("The backup changed after integrity verification.")
    return parse_manifest(metadata["manifest.json"])


async def transactional_media_members(
    reader: BackupReader,
    manifest: BackupManifest,
    media: MediaFiles,
    workspace: BackupWorkspace,
    undo: MediaUndo,
    *,
    expected_digest: str | None = None,
) -> AsyncGenerator[ArchiveMember]:
    """Write media before the database consumer reaches its commit point."""
    refs = {f"media/{ref.asset_id}": ref for ref in manifest.media}
    async with aclosing(reader.members()) as members:
        async for member in members:
            if member.name.startswith("data/"):
                yield member
            elif member.name in refs:
                ref = refs[member.name]
                try:
                    original = await workspace.save(media.open(ref))
                except MediaFileMissingError:
                    original = None
                undo.append((ref, original))
                await media.write(ref, member.chunks)
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
) -> None:
    """Verify and restore with reversible media writes inside the transaction."""
    expected_digest = await store.archive_digest(backup_id)
    manifest = await archive_manifest(store, backup_id)
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


class RestoreBackup(AuthorisedUseCase[RestoreBackupCommand, None, BackupPermission]):
    """Administrative instance restoration."""

    required_permission = BackupPermission.RESTORE

    def __init__(
        self,
        store: BackupStore,
        restorer: DatabaseRestorer,
        media: MediaFiles,
        workspace: BackupWorkspace,
        authorization: AuthorizationPort,
    ) -> None:
        super().__init__(authorization)
        self._store, self._restorer, self._media, self._workspace = (
            store,
            restorer,
            media,
            workspace,
        )

    async def _handle(self, request: RestoreBackupCommand, actor: Actor) -> None:
        await restore_verified_backup(
            self._store,
            self._restorer,
            self._media,
            self._workspace,
            request.backup_id,
            replace=request.replace,
            setup_only=request.setup_only,
        )
        logger.warning(
            "instance backup restored",
            backup_id=request.backup_id,
            actor_id=actor.id,
            replace=request.replace,
        )

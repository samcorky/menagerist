import json
from contextlib import aclosing
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

import structlog

from app.modules.backup.application.restore_backup import (
    archive_manifest,
    cleanup_media,
    rollback_media,
    transactional_media_members,
)
from app.modules.backup.domain.backup import BackupScope
from app.modules.backup.domain.errors import CorruptBackupError, IncompatibleBackupError
from app.modules.backup.ports.user_database_restorer import UserDatabaseRestorer
from app.shared_kernel.access import Access, Content
from app.shared_kernel.guarded import GuardedCommandHandler

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.application.restore_backup import MediaUndo
    from app.modules.backup.domain.backup import BackupManifest
    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_workspace import BackupWorkspace
    from app.modules.backup.ports.media_files import MediaFiles
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


_MAX_ROW_BYTES = 16 * 1024 * 1024


def _media_record(line: bytes) -> tuple[UUID, tuple[object, object, object]]:
    if len(line) > _MAX_ROW_BYTES:
        raise CorruptBackupError("User media asset row exceeds the size limit.")
    try:
        row = json.loads(line)
        return UUID(row["id"]), (row["status"], row["size"], row["sha256"])
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise CorruptBackupError("Invalid user media asset record.") from exc


async def _media_records(
    chunks: AsyncIterator[bytes],
) -> dict[UUID, tuple[object, object, object]]:
    assets: dict[UUID, tuple[object, object, object]] = {}
    pending = bytearray()
    async for chunk in chunks:
        pending.extend(chunk)
        while (end := pending.find(b"\n")) != -1:
            line = bytes(pending[:end])
            del pending[: end + 1]
            asset_id, record = _media_record(line)
            if asset_id in assets:
                raise CorruptBackupError("Duplicate user media asset record.")
            assets[asset_id] = record
        if len(pending) > _MAX_ROW_BYTES:
            raise CorruptBackupError("User media asset row exceeds the size limit.")
    if pending:
        raise CorruptBackupError("Unterminated media asset record.")
    return assets


async def _validate_media_records(
    store: BackupStore, backup_id: UUID, manifest: BackupManifest
) -> None:
    """Reject arbitrary media destinations before any database or file mutation."""
    assets: dict[UUID, tuple[object, object, object]] = {}
    data_finished = False
    async with aclosing((await store.open(backup_id)).members()) as members:
        async for member in members:
            if member.name.startswith("media/"):
                data_finished = True
            elif member.name.startswith("data/") and data_finished:
                raise CorruptBackupError("Content tables must precede media originals.")
            if member.name == "data/media_assets.ndjson":
                assets = await _media_records(member.chunks)
            else:
                async for _ in member.chunks:
                    pass
    expected = {
        ref.asset_id: (ref.status, ref.size, ref.sha256) for ref in manifest.media
    }
    if assets != expected:
        raise CorruptBackupError(
            "User archive media records do not match its originals."
        )


@dataclass(frozen=True, kw_only=True)
class ImportUserDataCommand:
    """Import a previously uploaded archive from the caller's private store."""

    backup_id: UUID


class ImportUserData(
    GuardedCommandHandler[UserDatabaseRestorer, ImportUserDataCommand, None]
):
    """Preserve identifiers while assigning all incoming content to the caller."""

    access: ClassVar[Access] = Content()

    def __init__(
        self,
        store: BackupStore,
        restorer: UserDatabaseRestorer,
        media: MediaFiles,
        workspace: BackupWorkspace,
        guard: AccessGuard,
    ) -> None:
        super().__init__(restorer, guard)
        self._store, self._restorer, self._media, self._workspace = (
            store,
            restorer,
            media,
            workspace,
        )

    async def _handle(self, request: ImportUserDataCommand, actor: Actor) -> None:
        """Verify before writes and compensate media if the database load fails."""
        self._guard.assert_can_modify(actor, actor.id)
        expected_digest = await self._store.archive_digest(request.backup_id)
        manifest = await archive_manifest(self._store, request.backup_id)
        if (
            manifest.scope != BackupScope.USER
            or manifest.owner_id is None
            or manifest.format != "ndjson"
            or manifest.format_version != 1
        ):
            raise IncompatibleBackupError(
                "A personal archive in format version 1 is required."
            )
        if manifest.alembic_revision != await self._restorer.schema_revision():
            raise IncompatibleBackupError(
                "The export migration revision differs from the target."
            )
        await _validate_media_records(self._store, request.backup_id, manifest)
        undo: MediaUndo = []
        try:
            async with aclosing(
                transactional_media_members(
                    await self._store.open(request.backup_id),
                    manifest,
                    self._media,
                    self._workspace,
                    undo,
                    expected_digest=expected_digest,
                )
            ) as members:
                await self._restorer.import_user(members, new_owner_id=actor.id)
        except BaseException:
            await rollback_media(self._media, self._workspace, undo)
            raise
        finally:
            await cleanup_media(self._workspace, undo)
        logger.info(
            "user data imported", actor_id=actor.id, backup_id=request.backup_id
        )

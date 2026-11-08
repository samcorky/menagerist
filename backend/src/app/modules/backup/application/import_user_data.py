import json
from contextlib import aclosing
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

import structlog

from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.application.restore_backup import (
    MANIFEST_PASSES,
    archive_manifest,
    cleanup_media,
    rollback_media,
    start_verify_phase,
    transactional_media_members,
)
from app.modules.backup.application.verify_backup import CompressedMeter
from app.modules.backup.domain.backup import BackupScope
from app.modules.backup.domain.errors import CorruptBackupError, IncompatibleBackupError
from app.modules.backup.ports.user_database_restorer import UserDatabaseRestorer
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.progress import NULL_PROGRESS, Phase

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.application.restore_backup import MediaUndo
    from app.modules.backup.domain.backup import BackupManifest
    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_workspace import BackupWorkspace
    from app.modules.backup.ports.media_files import MediaFiles
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.progress import ProgressReporter

logger = structlog.get_logger()

IMPORT_PLAN = (
    Phase(key="verify", label="Checking the export", weight=2, unit="bytes"),
    Phase(key="database", label="Importing your items", weight=3),
    Phase(key="media", label="Importing photos and files", weight=5),
)
# archive_manifest's passes plus the media-record validation pass.
IMPORT_VERIFY_PASSES = MANIFEST_PASSES + 1


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
    store: BackupStore,
    backup_id: UUID,
    manifest: BackupManifest,
    progress: ProgressReporter = NULL_PROGRESS,
) -> None:
    """Reject arbitrary media destinations before any database or file mutation."""
    assets: dict[UUID, tuple[object, object, object]] = {}
    data_finished = False
    reader = await store.open(backup_id)
    meter = CompressedMeter(reader, progress)
    async with aclosing(reader.members()) as members:
        async for member in members:
            if member.name.startswith("media/"):
                data_finished = True
            elif member.name.startswith("data/") and data_finished:
                raise CorruptBackupError("Content tables must precede media originals.")
            if member.name == "data/media_assets.ndjson":
                assets = await _media_records(member.chunks)
            else:
                async for _ in member.chunks:
                    await meter.tick()
            await meter.tick()
    await meter.tick()
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


class ImportUserData(CommandHandler[UserDatabaseRestorer, ImportUserDataCommand, None]):
    """Preserve identifiers while assigning all incoming content to the caller."""

    access: ClassVar[Access] = Content(BackupPermission.IMPORT_OWN_DATA)

    def __init__(
        self,
        store: BackupStore,
        restorer: UserDatabaseRestorer,
        media: MediaFiles,
        workspace: BackupWorkspace,
        guard: AccessGuard,
        progress: ProgressReporter | None = None,
    ) -> None:
        super().__init__(restorer, guard)
        self._progress = progress or NULL_PROGRESS
        self._store, self._restorer, self._media, self._workspace = (
            store,
            restorer,
            media,
            workspace,
        )

    async def _handle(self, request: ImportUserDataCommand, actor: Actor) -> None:
        """Verify before writes and compensate media if the database load fails."""
        self._guard.assert_can_modify(actor, actor.id)
        await self._progress.begin(IMPORT_PLAN)
        await start_verify_phase(
            self._store,
            request.backup_id,
            self._progress,
            passes=IMPORT_VERIFY_PASSES,
        )
        expected_digest = await self._store.archive_digest(request.backup_id)
        manifest = await archive_manifest(
            self._store, request.backup_id, self._progress
        )
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
        await _validate_media_records(
            self._store, request.backup_id, manifest, self._progress
        )
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
                    progress=self._progress,
                )
            ) as members:
                await self._restorer.import_user(members, new_owner_id=actor.id)
        except BaseException:
            await rollback_media(self._media, self._workspace, undo)
            raise
        finally:
            await cleanup_media(self._workspace, undo)
        await self._progress.done()
        logger.info(
            "user data imported", actor_id=actor.id, backup_id=request.backup_id
        )

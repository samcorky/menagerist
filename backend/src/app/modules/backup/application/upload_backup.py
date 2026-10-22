from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from uuid import uuid7

from app.modules.backup.application.archive import analyse_members, parse_manifest
from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.application.verify_backup import _scan
from app.modules.backup.domain.backup import BackupScope, BackupSummary
from app.modules.backup.domain.errors import CorruptBackupError, IncompatibleBackupError
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.guarded import GuardedUseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_workspace import BackupWorkspace
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class UploadBackupCommand:
    """Incoming compressed archive stream."""

    stream: AsyncIterator[bytes]


async def _limited(stream: AsyncIterator[bytes], max_size: int) -> AsyncIterator[bytes]:
    size = 0
    async for chunk in stream:
        size += len(chunk)
        if size > max_size:
            raise CorruptBackupError("Backup upload exceeds the configured size limit.")
        yield chunk


async def upload_verified_backup(
    store: BackupStore,
    workspace: BackupWorkspace,
    stream: AsyncIterator[bytes],
    max_size: int,
    *,
    allowed_scope: BackupScope = BackupScope.INSTANCE,
) -> BackupSummary:
    """Verify private staged bytes before publishing an archive."""
    key = await workspace.save(_limited(stream, max_size))
    try:
        digests, metadata, findings = await _scan(await workspace.open_archive(key))
        report = analyse_members(
            digests, metadata.get("manifest.json"), metadata.get("checksums.sha256")
        )
        if findings or report.findings:
            raise CorruptBackupError("Uploaded backup failed integrity verification.")
        manifest = parse_manifest(metadata["manifest.json"])
        if (
            manifest.scope != allowed_scope
            or manifest.format != "ndjson"
            or manifest.format_version != 1
        ):
            raise IncompatibleBackupError(
                "The uploaded backup has an incompatible scope or format."
            )
        writer = await store.begin(uuid7())
        try:
            reader = await workspace.open_archive(key)
            async with aclosing(reader.members()) as members:
                async for member in members:
                    if member.name not in {"manifest.json", "checksums.sha256"}:
                        await writer.add(member.name, member.chunks)
            return (await writer.finish(manifest)).summary
        except BaseException:
            await writer.abort()
            raise
    finally:
        await workspace.remove(key)


class UploadBackup(GuardedUseCase[UploadBackupCommand, BackupSummary]):
    """Publish a verified administrative instance upload."""

    access: ClassVar[Access] = Requires(BackupPermission.CREATE)

    def __init__(
        self,
        store: BackupStore,
        workspace: BackupWorkspace,
        guard: AccessGuard,
        *,
        max_upload_size: int = 8 * 1024**3,
    ) -> None:
        self._guard = guard
        self._store, self._workspace, self._max_size = store, workspace, max_upload_size

    async def _handle(
        self, request: UploadBackupCommand, actor: Actor
    ) -> BackupSummary:
        return await upload_verified_backup(
            self._store, self._workspace, request.stream, self._max_size
        )

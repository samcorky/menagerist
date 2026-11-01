from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.backup import BackupSummary
from app.modules.backup.domain.errors import BackupNotFoundError
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class OpenBackupQuery:
    """Identify a committed archive for download."""

    backup_id: UUID


@dataclass(frozen=True, kw_only=True)
class OpenedBackup:
    """A summary and its raw compressed download stream."""

    summary: BackupSummary
    chunks: AsyncIterator[bytes]


class OpenBackup(UseCase[OpenBackupQuery, OpenedBackup]):
    """Resolve the commit marker before returning download bytes."""

    access: ClassVar[Access] = Requires(BackupPermission.READ)

    def __init__(self, store: BackupStore, guard: AccessGuard) -> None:
        self._guard = guard
        self._store = store

    async def _handle(self, request: OpenBackupQuery, actor: Actor) -> OpenedBackup:
        for summary in await self._store.list():
            if summary.id == request.backup_id:
                return OpenedBackup(
                    summary=summary, chunks=self._store.read_bytes(summary.id)
                )
        raise BackupNotFoundError(f"Backup {request.backup_id} was not found.")

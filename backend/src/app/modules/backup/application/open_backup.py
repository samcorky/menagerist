from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.backup import BackupSummary
from app.modules.backup.domain.errors import BackupNotFoundError
from app.shared_kernel.cqrs import AuthorisedUseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorization import AuthorizationPort


@dataclass(frozen=True, kw_only=True)
class OpenBackupQuery:
    """Identify a committed archive for download."""

    backup_id: UUID


@dataclass(frozen=True, kw_only=True)
class OpenedBackup:
    """A summary and its raw compressed download stream."""

    summary: BackupSummary
    chunks: AsyncIterator[bytes]


class OpenBackup(AuthorisedUseCase[OpenBackupQuery, OpenedBackup, BackupPermission]):
    """Resolve the commit marker before returning download bytes."""

    required_permission = BackupPermission.READ

    def __init__(self, store: BackupStore, authorization: AuthorizationPort) -> None:
        super().__init__(authorization)
        self._store = store

    async def _handle(self, request: OpenBackupQuery, actor: Actor) -> OpenedBackup:
        for summary in await self._store.list():
            if summary.id == request.backup_id:
                return OpenedBackup(
                    summary=summary, chunks=self._store.read_bytes(summary.id)
                )
        raise BackupNotFoundError(f"Backup {request.backup_id} was not found.")

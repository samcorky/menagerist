from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

import structlog

from app.modules.backup.application.permissions import BackupPermission
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.guarded import GuardedUseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class DeleteBackupCommand:
    """Identify an instance backup to remove."""

    backup_id: UUID


class DeleteBackup(GuardedUseCase[DeleteBackupCommand, None]):
    """Remove an archive's commit marker before its bytes."""

    access: ClassVar[Access] = Requires(BackupPermission.DELETE)

    def __init__(self, store: BackupStore, guard: AccessGuard) -> None:
        self._guard = guard
        self._store = store

    async def _handle(self, request: DeleteBackupCommand, actor: Actor) -> None:
        await self._store.delete(request.backup_id)
        logger.info(
            "instance backup deleted", backup_id=request.backup_id, actor_id=actor.id
        )

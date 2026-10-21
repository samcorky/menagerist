from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from app.modules.backup.application.permissions import BackupPermission
from app.shared_kernel.cqrs import AuthorisedUseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class DeleteBackupCommand:
    """Identify an instance backup to remove."""

    backup_id: UUID


class DeleteBackup(AuthorisedUseCase[DeleteBackupCommand, None, BackupPermission]):
    """Remove an archive's commit marker before its bytes."""

    required_permission = BackupPermission.DELETE

    def __init__(self, store: BackupStore, authorisation: AuthorisationPort) -> None:
        super().__init__(authorisation)
        self._store = store

    async def _handle(self, request: DeleteBackupCommand, actor: Actor) -> None:
        await self._store.delete(request.backup_id)
        logger.info(
            "instance backup deleted", backup_id=request.backup_id, actor_id=actor.id
        )

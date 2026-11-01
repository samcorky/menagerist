from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

import structlog

from app.modules.backup.application.export_user_data import prune_user_exports
from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.errors import BackupNotFoundError
from app.modules.backup.ports.backup_store import BackupStore
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class DeleteUserExportCommand:
    """Identify one of the caller's personal exports to remove."""

    backup_id: UUID


class DeleteUserExport(CommandHandler[BackupStore, DeleteUserExportCommand, None]):
    """Delete an unexpired export from the caller's private namespace."""

    access: ClassVar[Access] = Content(BackupPermission.EXPORT_OWN_DATA)

    def __init__(
        self, store: BackupStore, guard: AccessGuard, *, ttl_hours: int = 24
    ) -> None:
        super().__init__(store, guard)
        self._ttl = timedelta(hours=ttl_hours)

    async def _handle(self, request: DeleteUserExportCommand, actor: Actor) -> None:
        """Prune expired exports, then delete the one named."""
        self._guard.assert_can_view(actor, actor.id)
        await prune_user_exports(self._uow, older_than=datetime.now(UTC) - self._ttl)
        if all(summary.id != request.backup_id for summary in await self._uow.list()):
            raise BackupNotFoundError(f"Export {request.backup_id} was not found.")
        await self._uow.delete(request.backup_id)
        logger.info(
            "user export deleted", actor_id=actor.id, backup_id=request.backup_id
        )

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.modules.backup.application.export_user_data import prune_user_exports
from app.modules.backup.application.open_backup import OpenedBackup
from app.modules.backup.domain.errors import BackupNotFoundError
from app.modules.backup.ports.backup_store import BackupStore
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class OpenUserExportQuery:
    """Download an archive from the caller's private export namespace."""

    backup_id: UUID


class OpenUserExport(QueryHandler[BackupStore, OpenUserExportQuery, OpenedBackup]):
    """Open committed exports within the caller's private namespace."""

    access: ClassVar[Access] = Content()

    def __init__(
        self, store: BackupStore, guard: AccessGuard, *, ttl_hours: int = 24
    ) -> None:
        super().__init__(store, guard)
        self._ttl = timedelta(hours=ttl_hours)

    async def _handle(self, request: OpenUserExportQuery, actor: Actor) -> OpenedBackup:
        """Prune expired exports and open one in the caller's namespace."""
        self._guard.assert_can_view(actor, actor.id)
        await prune_user_exports(self._repos, older_than=datetime.now(UTC) - self._ttl)
        for summary in await self._repos.list():
            if summary.id == request.backup_id:
                return OpenedBackup(
                    summary=summary, chunks=self._repos.read_bytes(summary.id)
                )
        raise BackupNotFoundError(f"Export {request.backup_id} was not found.")

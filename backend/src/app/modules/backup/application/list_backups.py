from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.backup import BackupSummary
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class ListBackupsQuery:
    """List committed instance backup summaries."""


class ListBackups(UseCase[ListBackupsQuery, list[BackupSummary]]):
    """Read committed summaries in newest-first order."""

    access: ClassVar[Access] = Requires(BackupPermission.READ)

    def __init__(self, store: BackupStore, guard: AccessGuard) -> None:
        self._guard = guard
        self._store = store

    async def _handle(
        self, request: ListBackupsQuery, actor: Actor
    ) -> list[BackupSummary]:
        return sorted(
            await self._store.list(),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )

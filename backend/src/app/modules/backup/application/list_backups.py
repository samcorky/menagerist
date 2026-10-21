from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.backup import BackupSummary
from app.shared_kernel.cqrs import AuthorisedUseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort


@dataclass(frozen=True, kw_only=True)
class ListBackupsQuery:
    """List committed instance backup summaries."""


class ListBackups(
    AuthorisedUseCase[ListBackupsQuery, list[BackupSummary], BackupPermission]
):
    """Read committed summaries in newest-first order."""

    required_permission = BackupPermission.READ

    def __init__(self, store: BackupStore, authorisation: AuthorisationPort) -> None:
        super().__init__(authorisation)
        self._store = store

    async def _handle(
        self, request: ListBackupsQuery, actor: Actor
    ) -> list[BackupSummary]:
        return sorted(
            await self._store.list(),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )

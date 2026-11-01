from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

from app.modules.backup.application.export_user_data import prune_user_exports
from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.backup import BackupSummary
from app.modules.backup.ports.backup_store import BackupStore
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class ListUserExportsQuery:
    """List the caller's available personal exports."""


@dataclass(frozen=True, kw_only=True)
class UserExport:
    """A personal export and when it stops being available."""

    summary: BackupSummary
    expires_at: datetime


class ListUserExports(
    QueryHandler[BackupStore, ListUserExportsQuery, list[UserExport]]
):
    """List unexpired exports from the caller's private namespace."""

    access: ClassVar[Access] = Content(BackupPermission.EXPORT_OWN_DATA)

    def __init__(
        self, store: BackupStore, guard: AccessGuard, *, ttl_hours: int = 24
    ) -> None:
        super().__init__(store, guard)
        self._ttl = timedelta(hours=ttl_hours)

    async def _handle(
        self, request: ListUserExportsQuery, actor: Actor
    ) -> list[UserExport]:
        """Prune expired exports, then return the rest newest first."""
        self._guard.assert_can_view(actor, actor.id)
        await prune_user_exports(self._repos, older_than=datetime.now(UTC) - self._ttl)
        summaries = sorted(
            await self._repos.list(),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        return [
            UserExport(summary=item, expires_at=item.created_at + self._ttl)
            for item in summaries
        ]

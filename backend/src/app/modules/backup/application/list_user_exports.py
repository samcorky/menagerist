from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from app.modules.backup.application.export_user_data import prune_user_exports
from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.backup import BackupSummary
from app.modules.backup.ports.backup_store import BackupStore
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import (
    Page,
    PagedQuery,
    SortOrder,
    page_rows,
    timestamp_value,
)

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


class UserExportSort(StrEnum):
    """What a person's exports can be sorted by: fields of the response."""

    CREATED_AT = "created_at"
    SIZE = "size"
    EXPIRES_AT = "expires_at"


@dataclass(kw_only=True)
class ListUserExportsQuery(PagedQuery[UserExportSort]):
    """List the caller's available personal exports, newest first unless told."""

    order: SortOrder = SortOrder.DESC


@dataclass(frozen=True, kw_only=True)
class UserExport:
    """A personal export and when it stops being available."""

    summary: BackupSummary
    expires_at: datetime


class ListUserExports(
    QueryHandler[BackupStore, ListUserExportsQuery, Page[UserExport]]
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
    ) -> Page[UserExport]:
        """Prune expired exports, then return a page of the rest."""
        self._guard.assert_can_view(actor, actor.id)
        await prune_user_exports(self._repos, older_than=datetime.now(UTC) - self._ttl)
        exports = [
            UserExport(summary=item, expires_at=item.created_at + self._ttl)
            for item in await self._repos.list()
        ]
        return page_rows(
            exports,
            request.page_request(UserExportSort.CREATED_AT),
            id_of=lambda export: export.summary.id,
            values={
                UserExportSort.CREATED_AT: lambda e: timestamp_value(
                    e.summary.created_at
                ),
                UserExportSort.SIZE: lambda export: export.summary.size,
                UserExportSort.EXPIRES_AT: lambda e: timestamp_value(e.expires_at),
            },
        )

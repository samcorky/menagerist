from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.backup import BackupSummary
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase
from app.shared_kernel.paging import (
    Page,
    SearchedPagedQuery,
    SortOrder,
    page_rows,
    timestamp_value,
)
from app.shared_kernel.text import matches_text

if TYPE_CHECKING:
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


class BackupSort(StrEnum):
    """What the backups can be sorted by: fields of the response."""

    CREATED_AT = "created_at"
    LABEL = "label"
    SIZE = "size"


@dataclass(kw_only=True)
class ListBackupsQuery(SearchedPagedQuery[BackupSort]):
    """List committed instance backup summaries, newest first unless told."""

    order: SortOrder = SortOrder.DESC


class ListBackups(UseCase[ListBackupsQuery, Page[BackupSummary]]):
    """Read committed summaries a page at a time."""

    access: ClassVar[Access] = Requires(BackupPermission.READ)

    def __init__(self, store: BackupStore, guard: AccessGuard) -> None:
        self._guard = guard
        self._store = store

    async def _handle(
        self, request: ListBackupsQuery, actor: Actor
    ) -> Page[BackupSummary]:
        return page_rows(
            [
                item
                for item in await self._store.list()
                if matches_text(request.q, item.label, item.app_version)
            ],
            request.page_request(BackupSort.CREATED_AT),
            id_of=lambda item: item.id,
            values={
                BackupSort.CREATED_AT: lambda item: timestamp_value(item.created_at),
                BackupSort.LABEL: lambda item: item.label.lower(),
                BackupSort.SIZE: lambda item: item.size,
            },
        )

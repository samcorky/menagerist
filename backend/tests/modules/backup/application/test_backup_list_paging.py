"""Sorting and paging of the backups and personal exports lists."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid7

import pytest

from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_user_database_snapshot import (
    InMemoryUserDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.application.export_user_data import (
    ExportUserData,
    ExportUserDataCommand,
)
from app.modules.backup.application.list_backups import (
    BackupSort,
    ListBackups,
    ListBackupsQuery,
)
from app.modules.backup.application.list_user_exports import (
    ListUserExports,
    ListUserExportsQuery,
    UserExportSort,
)
from app.modules.backup.domain.backup import BackupSummary
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.paging import SortOrder

if TYPE_CHECKING:
    from app.modules.backup.adapters.storage.in_memory_backup_store import (
        InMemoryBackupStore as Store,
    )


def _summary(label: str, size: int, age: timedelta) -> BackupSummary:
    return BackupSummary(
        id=uuid7(),
        label=label,
        size=size,
        created_at=datetime.now(UTC) - age,
        alembic_revision="rev",
        app_version="test",
    )


@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", list(BackupSort))
async def test_backups_page_through_every_sort_key(
    sort: BackupSort, order: SortOrder
) -> None:
    """Following `next` visits each backup once, whatever the key and direction."""
    store = InMemoryBackupStore()
    for n, (label, size) in enumerate([("b", 3), ("A", 1), ("c", 2)]):
        summary = _summary(label, size, timedelta(hours=n))
        store.summaries[summary.id] = summary
    use_case = ListBackups(store, InMemoryAccessGuard())

    seen: list[UUID] = []
    query = ListBackupsQuery(limit=2, sort=sort, order=order)
    while True:
        page = await use_case.handle(query, SYSTEM_ACTOR)
        assert page.total == 3
        seen.extend(item.id for item in page.items)
        if page.next is None:
            break
        query = ListBackupsQuery(after=page.next, limit=2, sort=sort, order=order)

    assert len(seen) == len(set(seen)) == 3


async def test_backups_run_newest_first_by_default() -> None:
    """With no sort or order, the most recent backup comes first."""
    store = InMemoryBackupStore()
    old, new = _summary("old", 1, timedelta(days=2)), _summary("new", 1, timedelta())
    store.summaries[old.id] = old
    store.summaries[new.id] = new

    page = await ListBackups(store, InMemoryAccessGuard()).handle(
        ListBackupsQuery(), SYSTEM_ACTOR
    )

    assert [item.id for item in page.items] == [new.id, old.id]


async def _export(store: Store, actor: Actor) -> UUID:
    created = await ExportUserData(
        store,
        InMemoryUserDatabaseSnapshot("rev", {}),
        InMemoryMediaFiles(),
        InMemoryAccessGuard(),
        app_version="test",
    ).handle(ExportUserDataCommand(), actor)
    return created.id


@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", list(UserExportSort))
async def test_exports_page_through_every_sort_key(
    sort: UserExportSort, order: SortOrder
) -> None:
    """Following `next` visits each export once, whatever the key and direction."""
    store, actor = InMemoryBackupStore(), Actor(id=uuid7())
    ids = [await _export(store, actor) for _ in range(3)]
    for n, backup_id in enumerate(ids):
        store.summaries[backup_id] = replace(
            store.summaries[backup_id],
            created_at=datetime.now(UTC) - timedelta(hours=n),
            size=10 - n,
        )
    use_case = ListUserExports(store, InMemoryAccessGuard(), ttl_hours=24)

    seen: list[UUID] = []
    query = ListUserExportsQuery(limit=2, sort=sort, order=order)
    while True:
        page = await use_case.handle(query, actor)
        assert page.total == 3
        seen.extend(item.summary.id for item in page.items)
        if page.next is None:
            break
        query = ListUserExportsQuery(after=page.next, limit=2, sort=sort, order=order)

    assert sorted(seen) == sorted(ids)


async def test_backups_search_the_label_and_the_version() -> None:
    """`q` ignores case and reads the label and the app version."""
    store = InMemoryBackupStore()
    nightly = replace(_summary("Nightly", 1, timedelta()), app_version="2026.11.4")
    manual = replace(
        _summary("Before upgrade", 1, timedelta()), app_version="2026.11.3"
    )
    for summary in (nightly, manual):
        store.summaries[summary.id] = summary
    use_case = ListBackups(store, InMemoryAccessGuard())

    async def ids(q: str) -> list[UUID]:
        page = await use_case.handle(ListBackupsQuery(q=q), SYSTEM_ACTOR)
        return [item.id for item in page.items]

    assert await ids("NIGHT") == [nightly.id]
    assert await ids("11.3") == [manual.id]
    assert await ids("zebra") == []

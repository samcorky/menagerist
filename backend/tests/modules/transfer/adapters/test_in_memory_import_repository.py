"""The in-memory twin of the import repository."""

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.transfer.adapters.persistence.in_memory_import_repository import (
    InMemoryItemImportRepository,
)
from app.modules.transfer.domain.item_import import (
    ImportOptions,
    ImportStatus,
    ItemImport,
)
from app.shared_kernel.content_filter import ContentFilter

ALICE = uuid.UUID(int=0xA1)
BOB = uuid.UUID(int=0xB2)
NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)


def _upload(owner: uuid.UUID = ALICE, hours: int = 24) -> ItemImport:
    return ItemImport.upload(
        owner_id=owner,
        filename="a.csv",
        size=1,
        now=NOW,
        keep_for=timedelta(hours=hours),
    )


async def test_reads_are_scoped_and_ordered() -> None:
    """Each person sees their own, newest first; the queue is oldest first."""
    repo = InMemoryItemImportRepository()
    first, second, bobs = _upload(), _upload(), _upload(BOB)
    for item in (first, second, bobs):
        await repo.add(item)
    second.queue(ImportOptions(item_type="t"), None, NOW)
    bobs.queue(ImportOptions(item_type="t"), None, NOW - timedelta(minutes=1))
    await repo.save(second)
    assert await repo.get(bobs.id, scope=ContentFilter.of(ALICE)) is None
    own = await repo.list_for_owner(scope=ContentFilter.of(ALICE))
    assert [i.id for i in own] == [second.id, first.id]
    queued = await repo.list_with_status(ImportStatus.QUEUED)
    assert [i.id for i in queued] == [bobs.id, second.id]


async def test_recent_owners_are_those_who_started_last() -> None:
    """Only started imports count, newest first, up to the limit."""
    repo = InMemoryItemImportRepository()
    items = [_upload(ALICE), _upload(BOB), _upload(ALICE)]
    for offset, item in enumerate(items):
        item.queue(ImportOptions(item_type="t"), None, NOW)
        if offset < 2:
            item.start(NOW + timedelta(minutes=offset))
        await repo.add(item)
    assert await repo.recent_owners(5) == [BOB, ALICE]
    assert await repo.recent_owners(1) == [BOB]


async def test_expired_and_deleted() -> None:
    """Expiry is by time alone; deleting a missing import is harmless."""
    repo = InMemoryItemImportRepository()
    old, fresh = _upload(hours=1), _upload(hours=48)
    await repo.add(old)
    await repo.add(fresh)
    expired = await repo.list_expired(NOW + timedelta(hours=2))
    assert [i.id for i in expired] == [old.id]
    await repo.delete(old.id)
    await repo.delete(old.id)
    assert await repo.get(old.id, scope=ContentFilter.everyone()) is None

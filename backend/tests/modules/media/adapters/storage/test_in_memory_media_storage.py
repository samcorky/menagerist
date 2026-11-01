"""The in-memory storage lists stored files the way the filesystem one does."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.media.adapters.storage.in_memory_media_storage import (
    InMemoryMediaStorage,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.modules.media.ports.media_storage import StoredFile
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _stream(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _asset() -> MediaAsset:
    return MediaAsset.create(
        owner_id=SYSTEM_ACTOR.id,
        filename="f.bin",
        content_type="application/octet-stream",
        size=0,
        sha256="",
    )


async def test_list_files_offers_only_files_older_than_the_cutoff() -> None:
    """A file stored just now is never offered; a backdated one is."""
    storage = InMemoryMediaStorage()
    old, fresh = _asset(), _asset()
    await storage.store(old.id, MediaStatus.STAGED, _stream(b"a"))
    await storage.store(fresh.id, MediaStatus.STAGED, _stream(b"b"))
    storage.modified_at[(old.id, "staged")] = datetime.now(UTC) - timedelta(hours=48)

    found = [
        item
        async for item in storage.list_files(
            older_than=datetime.now(UTC) - timedelta(hours=24)
        )
    ]

    assert found == [StoredFile(asset_id=old.id, status=MediaStatus.STAGED)]


async def test_a_moved_file_keeps_its_age_and_a_deleted_one_is_forgotten() -> None:
    """Moving does not make an old file look new; deleting drops it from the list."""
    storage = InMemoryMediaStorage()
    asset = _asset()
    await storage.store(asset.id, MediaStatus.STAGED, _stream(b"a"))
    storage.modified_at[(asset.id, "staged")] = datetime.now(UTC) - timedelta(hours=48)
    await storage.move(asset.id, MediaStatus.STAGED, MediaStatus.ATTACHED)
    cutoff = datetime.now(UTC) - timedelta(hours=24)

    assert [item async for item in storage.list_files(older_than=cutoff)] == [
        StoredFile(asset_id=asset.id, status=MediaStatus.ATTACHED)
    ]

    await storage.delete(asset.id, MediaStatus.ATTACHED)
    assert [item async for item in storage.list_files(older_than=cutoff)] == []

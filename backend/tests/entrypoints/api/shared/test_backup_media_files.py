import hashlib
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.backup_media_files import BackupMediaFiles
from app.modules.backup.domain.errors import MediaFileMissingError
from app.modules.media.adapters.persistence.in_memory_media_asset_repository import (
    InMemoryMediaAssetRepository,
)
from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def test_user_export_lists_only_own_originals(tmp_path: Path) -> None:
    """A per-user backup must never enumerate another account's media."""
    repository = InMemoryMediaAssetRepository()
    owner_id = uuid7()
    own = MediaAsset.create(
        owner_id=owner_id,
        filename="own.png",
        content_type="image/png",
        size=3,
        sha256=hashlib.sha256(b"own").hexdigest(),
    )
    foreign = MediaAsset.create(
        owner_id=uuid7(),
        filename="foreign.png",
        content_type="image/png",
        size=3,
        sha256=hashlib.sha256(b"not").hexdigest(),
    )
    await repository.add(own)
    await repository.add(foreign)
    bridge = BackupMediaFiles(
        repository,
        LocalFilesystemMediaStorage(tmp_path),
        scope=ContentFilter.of(owner_id),
    )
    assert [ref.asset_id for ref in await bridge.list_files()] == [own.id]


@pytest.mark.parametrize("status", list(MediaStatus))
async def test_originals_round_trip_in_recorded_bucket(
    tmp_path: Path, status: MediaStatus
) -> None:
    """All statuses retain originals without archiving derived thumbnails."""
    repository = InMemoryMediaAssetRepository()
    storage = LocalFilesystemMediaStorage(tmp_path)
    bridge = BackupMediaFiles(repository, storage)
    asset = MediaAsset.create(
        owner_id=uuid7(),
        filename="original.png",
        content_type="image/png",
        size=8,
        sha256=hashlib.sha256(b"original").hexdigest(),
    )
    asset.status = status
    await repository.add(asset)
    refs = await bridge.list_files()
    assert len(refs) == 1
    ref = refs[0]
    assert (ref.asset_id, ref.status, ref.size, ref.sha256) == (
        asset.id,
        status.value,
        asset.size,
        asset.sha256,
    )
    await bridge.write(ref, _chunks(b"original"))
    await storage.store_thumbnail(asset.id, status, b"thumbnail")
    assert b"".join([chunk async for chunk in bridge.open(ref)]) == b"original"
    assert len(await bridge.list_files()) == 1
    assert list((tmp_path / status.value).glob("*/*"))
    await bridge.remove(ref)
    with pytest.raises(MediaFileMissingError, match=str(asset.id)):
        _ = [chunk async for chunk in bridge.open(ref)]

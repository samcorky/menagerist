import hashlib
from typing import TYPE_CHECKING

import pytest

from app.modules.media.adapters.storage.local_filesystem import (
    LocalFilesystemMediaStorage,
)
from app.modules.media.domain.errors import MediaFileTooLargeError
from app.modules.media.domain.media_asset import MediaAsset, MediaStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


async def _stream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


def _storage(tmp_path: Path) -> LocalFilesystemMediaStorage:
    return LocalFilesystemMediaStorage(tmp_path)


def _asset() -> MediaAsset:
    return MediaAsset.create(
        filename="f.bin", content_type="application/octet-stream", size=0, sha256=""
    )


async def test_store_writes_file_and_returns_size_and_sha256(tmp_path: Path) -> None:
    """store() persists the stream and returns correct (size, sha256)."""
    storage = _storage(tmp_path)
    asset = _asset()
    data = b"hello world"

    size, sha256 = await storage.store(asset.id, MediaStatus.STAGED, _stream(data))

    assert size == len(data)
    assert sha256 == hashlib.sha256(data).hexdigest()


async def test_store_file_is_readable_at_sharded_path(tmp_path: Path) -> None:
    """store() places the file under {status}/{shard}/{asset_id}."""
    storage = _storage(tmp_path)
    asset = _asset()
    data = b"test content"

    await storage.store(asset.id, MediaStatus.STAGED, _stream(data))

    shard = hashlib.sha256(asset.id.bytes).hexdigest()[:2]
    expected = tmp_path / "staged" / shard / str(asset.id)
    assert expected.exists()
    assert expected.read_bytes() == data


async def test_store_no_tmp_file_left_on_success(tmp_path: Path) -> None:
    """store() removes the .tmp file after a successful write."""
    storage = _storage(tmp_path)
    asset = _asset()

    await storage.store(asset.id, MediaStatus.STAGED, _stream(b"x"))

    shard = tmp_path / "staged" / hashlib.sha256(asset.id.bytes).hexdigest()[:2]
    tmp_files = list(shard.glob("*.tmp"))
    assert tmp_files == []


async def test_store_raises_and_cleans_up_when_too_large(tmp_path: Path) -> None:
    """store() raises MediaFileTooLargeError and removes the .tmp file."""
    storage = _storage(tmp_path)
    asset = _asset()

    with pytest.raises(MediaFileTooLargeError):
        await storage.store(
            asset.id, MediaStatus.STAGED, _stream(b"x" * 20), max_size=10
        )

    shard = tmp_path / "staged" / hashlib.sha256(asset.id.bytes).hexdigest()[:2]
    # Neither the final file nor the tmp file should remain.
    assert not (shard / str(asset.id)).exists()
    tmp_files = list(shard.glob("*.tmp")) if shard.exists() else []
    assert tmp_files == []


async def test_retrieve_streams_stored_content(tmp_path: Path) -> None:
    """retrieve() yields back exactly the bytes that were stored."""
    storage = _storage(tmp_path)
    asset = _asset()
    data = b"streaming content"

    await storage.store(asset.id, MediaStatus.STAGED, _stream(data))

    received = b""
    async for chunk in storage.retrieve(asset.id, MediaStatus.STAGED):
        received += chunk

    assert received == data


async def test_retrieve_works_in_chunks(tmp_path: Path) -> None:
    """retrieve() handles content larger than the internal chunk size."""
    storage = _storage(tmp_path)
    asset = _asset()
    data = b"z" * (128 * 1024)  # 128 KiB — larger than the 64 KiB chunk size

    await storage.store(asset.id, MediaStatus.STAGED, _stream(data))

    received = b""
    async for chunk in storage.retrieve(asset.id, MediaStatus.STAGED):
        received += chunk

    assert received == data


async def test_move_relocates_file_between_buckets(tmp_path: Path) -> None:
    """move() puts the file in the destination bucket and removes it from source."""
    storage = _storage(tmp_path)
    asset = _asset()
    data = b"moving"

    await storage.store(asset.id, MediaStatus.STAGED, _stream(data))
    await storage.move(asset.id, MediaStatus.STAGED, MediaStatus.ATTACHED)

    shard = hashlib.sha256(asset.id.bytes).hexdigest()[:2]
    src = tmp_path / "staged" / shard / str(asset.id)
    dst = tmp_path / "attached" / shard / str(asset.id)
    assert not src.exists()
    assert dst.exists()
    assert dst.read_bytes() == data


async def test_move_content_survives_intact(tmp_path: Path) -> None:
    """retrieve() after move() returns the original bytes unchanged."""
    storage = _storage(tmp_path)
    asset = _asset()
    data = b"survive the move"

    await storage.store(asset.id, MediaStatus.STAGED, _stream(data))
    await storage.move(asset.id, MediaStatus.STAGED, MediaStatus.ATTACHED)

    received = b""
    async for chunk in storage.retrieve(asset.id, MediaStatus.ATTACHED):
        received += chunk

    assert received == data


async def test_delete_removes_stored_file(tmp_path: Path) -> None:
    """delete() removes the file from disk."""
    storage = _storage(tmp_path)
    asset = _asset()

    await storage.store(asset.id, MediaStatus.STAGED, _stream(b"gone"))
    shard = hashlib.sha256(asset.id.bytes).hexdigest()[:2]
    path = tmp_path / "staged" / shard / str(asset.id)
    assert path.exists()

    await storage.delete(asset.id, MediaStatus.STAGED)

    assert not path.exists()


async def test_delete_is_idempotent_for_missing_file(tmp_path: Path) -> None:
    """delete() does not raise if the file is already absent."""
    storage = _storage(tmp_path)
    asset = _asset()

    await storage.delete(asset.id, MediaStatus.STAGED)  # should not raise


async def test_store_multipart_stream_concatenates_chunks(tmp_path: Path) -> None:
    """store() correctly concatenates multiple stream chunks."""
    storage = _storage(tmp_path)
    asset = _asset()
    parts = [b"part1-", b"part2-", b"part3"]
    data = b"".join(parts)

    size, sha256 = await storage.store(asset.id, MediaStatus.STAGED, _stream(*parts))

    assert size == len(data)
    assert sha256 == hashlib.sha256(data).hexdigest()
    shard = hashlib.sha256(asset.id.bytes).hexdigest()[:2]
    path = tmp_path / "staged" / shard / str(asset.id)
    assert path.read_bytes() == data

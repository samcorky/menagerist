import hashlib
import os
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.modules.backup.adapters.storage.in_memory_backup_reader import byte_chunks
from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.domain.backup import BackupManifest
from app.modules.backup.domain.errors import (
    BackupNotFoundError,
    BackupStorageError,
    CorruptBackupError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def manifest() -> BackupManifest:
    """Build valid metadata for an otherwise empty archive."""
    return BackupManifest(
        app_version="test",
        alembic_revision="head",
        label="manual",
        created_at=datetime.now(UTC),
        created_by=uuid7(),
    )


async def test_archive_commit_stream_digest_and_delete(tmp_path: Path) -> None:
    """A committed archive retains member order and both digest layers."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    assert await store.list() == []
    digest = await writer.add("data/users.ndjson", byte_chunks(b'{"id":1}\n'))
    assert digest.lines == 1
    stored = await writer.finish(manifest())
    assert await store.list() == [stored.summary]
    reader = await store.open(backup_id)
    members = {
        member.name: b"".join([part async for part in member.chunks])
        async for member in reader.members()
    }
    assert members["data/users.ndjson"] == b'{"id":1}\n'
    assert list(members)[-2:] == ["checksums.sha256", "manifest.json"]
    raw = b"".join([part async for part in store.read_bytes(backup_id)])
    assert (
        await reader.archive_digest()
        == hashlib.sha256(raw).hexdigest()
        == stored.sha256
    )
    assert await store.archive_digest(backup_id) == stored.sha256
    assert not list((tmp_path / ".staging").iterdir())
    await store.delete(backup_id)
    assert await store.list() == []
    with pytest.raises(BackupNotFoundError):
        await store.open(backup_id)


async def test_abort_and_orphan_cleanup(tmp_path: Path) -> None:
    """Abort clears staging and dry-run reports orphans without deleting."""
    store = LocalDirectoryBackupStore(tmp_path)
    writer = await store.begin(uuid7())
    await writer.add("data/users.ndjson", byte_chunks(b"{}\n"))
    await writer.abort()
    assert not list((tmp_path / ".staging").iterdir())
    orphan = tmp_path / "instance" / f"{uuid7()}.tar.gz"
    orphan.write_bytes(b"orphan")
    before = datetime.now(UTC) + timedelta(hours=1)
    assert await store.cleanup_orphans(before=before, dry_run=True)
    assert orphan.exists()
    assert await store.cleanup_orphans(before=before, dry_run=False)
    assert not orphan.exists()


async def test_truncated_gzip_trailer_is_corrupt(tmp_path: Path) -> None:
    """Gzip trailer truncation cannot be hidden by tar end markers."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.finish(manifest())
    path = tmp_path / "instance" / f"{backup_id}.tar.gz"
    path.write_bytes(path.read_bytes()[:-5])
    reader = await store.open(backup_id)
    with pytest.raises(CorruptBackupError):
        _ = [member async for member in reader.members()]
    assert (
        await reader.archive_digest() == hashlib.sha256(path.read_bytes()).hexdigest()
    )


async def test_unreadable_summary_is_reported_and_never_pruned(tmp_path: Path) -> None:
    """A corrupt commit marker protects its archive from orphan removal."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.finish(manifest())
    path = tmp_path / "instance" / f"{backup_id}.json"
    path.write_bytes(b"not json")
    assert await store.list() == []
    assert await store.unreadable() == [path.name]
    assert await store.cleanup_orphans(before=datetime.now(UTC), dry_run=False) == []
    assert (tmp_path / "instance" / f"{backup_id}.tar.gz").exists()


async def test_active_writer_survives_orphan_cleanup(tmp_path: Path) -> None:
    """A held operation lease protects even apparently stale staging."""
    store = LocalDirectoryBackupStore(tmp_path)
    writer = await store.begin(uuid7())
    before = datetime.now(UTC) + timedelta(days=1)
    assert await store.cleanup_orphans(before=before, dry_run=False) == []
    await writer.finish(manifest())
    assert len(await store.list()) == 1


async def test_failed_member_is_removed_and_abort_closes_partial(
    tmp_path: Path,
) -> None:
    """Upstream failure leaves neither a member spool nor a committed archive."""
    store = LocalDirectoryBackupStore(tmp_path)
    writer = await store.begin(uuid7())

    async def broken() -> AsyncIterator[bytes]:
        yield b"partial"
        raise OSError("upstream failure")

    with pytest.raises(OSError, match="upstream failure"):
        await writer.add("data/users.ndjson", broken())
    assert not list((tmp_path / ".staging").rglob("*.member"))
    await writer.abort()
    await writer.abort()
    assert await store.list() == []
    assert not list((tmp_path / ".staging").iterdir())


async def test_missing_store_and_sidecars(tmp_path: Path) -> None:
    """Missing archives raise domain errors and optional sidecars may be absent."""
    store = LocalDirectoryBackupStore(tmp_path / "absent")
    assert await store.list() == []
    assert await store.unreadable() == []
    assert await store.cleanup_orphans(before=datetime.now(UTC), dry_run=False) == []
    backup_id = uuid7()
    with pytest.raises(BackupNotFoundError):
        await store.delete(backup_id)
    with pytest.raises(BackupNotFoundError):
        await store.archive_digest(backup_id)
    with pytest.raises(BackupNotFoundError):
        _ = [part async for part in store.read_bytes(backup_id)]
    writer = await store.begin(backup_id)
    await writer.finish(manifest())
    sidecar = tmp_path / "absent" / "instance" / f"{backup_id}.sha256"
    sidecar.write_bytes(b"")
    assert await store.archive_digest(backup_id) is None
    sidecar.unlink()
    assert await store.archive_digest(backup_id) is None
    await store.delete(backup_id)


@pytest.mark.parametrize("kind", [tarfile.DIRTYPE, tarfile.SYMTYPE, tarfile.LNKTYPE])
async def test_reader_rejects_nonregular_members(tmp_path: Path, kind: bytes) -> None:
    """Directories and links are rejected before their contents are exposed."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.finish(manifest())
    path = tmp_path / "instance" / f"{backup_id}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("data/users.ndjson")
        info.type = kind
        info.linkname = "outside"
        archive.addfile(info)
    reader = await store.open(backup_id)
    with pytest.raises(CorruptBackupError, match="regular"):
        _ = [member async for member in reader.members()]


async def test_reader_skips_unconsumed_members_and_requires_complete_digest(
    tmp_path: Path,
) -> None:
    """Advancing drains a member, while digest access requires full validation."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.add("data/users.ndjson", byte_chunks(b"first"))
    await writer.add("data/nodes.ndjson", byte_chunks(b"second"))
    stored = await writer.finish(manifest())
    reader = await store.open(backup_id)
    with pytest.raises(CorruptBackupError, match="completely"):
        await reader.archive_digest()
    names = [member.name async for member in reader.members()]
    assert names[:2] == ["data/users.ndjson", "data/nodes.ndjson"]
    assert await reader.archive_digest() == stored.sha256


async def test_in_memory_open_uses_actual_archive_bytes() -> None:
    """The in-memory adapter cannot hide compressed-byte tampering."""
    from app.modules.backup.adapters.storage.in_memory_backup_store import (
        InMemoryBackupStore,
    )

    store = InMemoryBackupStore()
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.finish(manifest())
    store.archives[backup_id] = b"damaged"
    reader = await store.open(backup_id)
    with pytest.raises(CorruptBackupError):
        _ = [member async for member in reader.members()]


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX mode bits are unavailable on Windows"
)
async def test_archives_and_sidecars_are_private(tmp_path: Path) -> None:
    """Password-bearing archives and their metadata have owner-only permissions."""
    store = LocalDirectoryBackupStore(tmp_path)
    writer = await store.begin(uuid7())
    await writer.finish(manifest())
    for path in (tmp_path / "instance").iterdir():
        assert path.stat().st_mode & 0o777 == 0o600


async def test_malformed_tar_is_reported_as_corrupt(tmp_path: Path) -> None:
    """Invalid tar headers are translated into the domain's corruption error."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.finish(manifest())
    path = tmp_path / "instance" / f"{backup_id}.tar.gz"
    import gzip

    path.write_bytes(gzip.compress(b"bad header"))
    reader = await store.open(backup_id)
    with pytest.raises(CorruptBackupError):
        _ = [member async for member in reader.members()]


async def test_unusable_backup_directory_has_operator_hint(tmp_path: Path) -> None:
    """A file in place of the volume yields an actionable storage error."""
    path = tmp_path / "file"
    path.write_bytes(b"blocked")
    store = LocalDirectoryBackupStore(path)
    with pytest.raises(BackupStorageError, match="chown 1000:1000"):
        await store.begin(uuid7())


async def test_summary_is_written_last_and_failure_leaves_only_orphans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure writing the commit marker never exposes an incomplete archive."""
    from app.modules.backup.adapters.storage.local_backup_writer import (
        LocalBackupWriter,
    )

    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    original = LocalBackupWriter._publish

    def fail_summary(self: LocalBackupWriter, destination: Path, data: bytes) -> None:
        if destination.suffix == ".json":
            assert (tmp_path / "instance" / f"{backup_id}.tar.gz").exists()
            assert (tmp_path / "instance" / f"{backup_id}.sha256").exists()
            raise OSError("summary failure")
        original(self, destination, data)

    monkeypatch.setattr(LocalBackupWriter, "_publish", fail_summary)
    with pytest.raises(OSError, match="summary failure"):
        await writer.finish(manifest())
    assert await store.list() == []
    assert await store.cleanup_orphans(before=datetime.now(UTC), dry_run=False) == []
    await writer.abort()
    assert (
        len(await store.cleanup_orphans(before=datetime.now(UTC), dry_run=False)) == 2
    )
    assert not list((tmp_path / "instance").iterdir())


async def test_stale_staging_removed_and_fresh_staging_kept(tmp_path: Path) -> None:
    """Cleanup uses age for abandoned staging and honours dry-run exactly."""
    staging = tmp_path / ".staging"
    staging.mkdir()
    stale = staging / "old"
    stale.mkdir()
    member = stale / "member"
    member.write_bytes(b"bytes")
    os.utime(member, (1, 1))
    os.utime(stale, (1, 1))
    fresh = staging / "fresh.tmp"
    fresh.write_bytes(b"new")
    before = datetime.now(UTC) - timedelta(hours=1)
    store = LocalDirectoryBackupStore(tmp_path)
    assert await store.cleanup_orphans(before=before, dry_run=True) == [
        str(Path(".staging/old"))
    ]
    assert member.read_bytes() == b"bytes"
    assert await store.cleanup_orphans(before=before, dry_run=False) == [
        str(Path(".staging/old"))
    ]
    assert fresh.exists()
    assert not stale.exists()


async def test_large_member_is_spooled_and_read_in_bounded_chunks(
    tmp_path: Path,
) -> None:
    """Member size increases disk usage without increasing buffered read size."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    part = b"x" * (1024 * 1024)

    async def large() -> AsyncIterator[bytes]:
        for _ in range(5):
            yield part

    digest = await writer.add("data/users.ndjson", large())
    assert digest.size == 5 * len(part)
    assert not list((tmp_path / ".staging").rglob("*.member"))
    await writer.finish(manifest())
    reader = await store.open(backup_id)
    size = 0
    async for member in reader.members():
        if member.name == "data/users.ndjson":
            async for chunk in member.chunks:
                assert len(chunk) <= len(part)
                size += len(chunk)
    assert size == digest.size


async def test_early_reader_close_hashes_remaining_compressed_bytes(
    tmp_path: Path,
) -> None:
    """Verification can close a rejected stream while retaining the archive hash."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.add("data/users.ndjson", byte_chunks(os.urandom(1024 * 1024)))
    stored = await writer.finish(manifest())
    reader = await store.open(backup_id)
    members = reader.members()
    assert (await anext(members)).name == "data/users.ndjson"
    await members.aclose()
    assert await reader.archive_digest() == stored.sha256


async def test_broken_compressed_payload_translates_error_and_retains_digest(
    tmp_path: Path,
) -> None:
    """Deflate errors remain domain errors and compressed hashing still completes."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.add("data/users.ndjson", byte_chunks(os.urandom(1024 * 1024)))
    await writer.finish(manifest())
    path = tmp_path / "instance" / f"{backup_id}.tar.gz"
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(data)
    reader = await store.open(backup_id)
    with pytest.raises(CorruptBackupError):
        _ = [member async for member in reader.members()]
    assert await reader.archive_digest() == hashlib.sha256(data).hexdigest()


async def test_summary_filename_must_match_its_id(tmp_path: Path) -> None:
    """Renamed summaries are unreadable rather than pointing at another archive."""
    store = LocalDirectoryBackupStore(tmp_path)
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.finish(manifest())
    path = tmp_path / "instance" / f"{backup_id}.json"
    renamed = path.with_name(f"{uuid7()}.json")
    path.rename(renamed)
    assert await store.list() == []
    assert await store.unreadable() == [renamed.name]


async def test_memory_orphan_cleanup_preserves_committed_archives() -> None:
    """In-memory cleanup models orphan collection and dry-run behaviour."""
    from app.modules.backup.adapters.storage.in_memory_backup_store import (
        InMemoryBackupStore,
    )

    store = InMemoryBackupStore()
    backup_id = uuid7()
    writer = await store.begin(backup_id)
    await writer.finish(manifest())
    orphan_id = uuid7()
    store.archives[orphan_id] = b"partial"
    assert await store.unreadable() == []
    assert await store.cleanup_orphans(before=datetime.now(UTC), dry_run=True) == [
        str(orphan_id)
    ]
    assert orphan_id in store.archives
    assert await store.cleanup_orphans(before=datetime.now(UTC), dry_run=False) == [
        str(orphan_id)
    ]
    assert set(store.archives) == {backup_id}

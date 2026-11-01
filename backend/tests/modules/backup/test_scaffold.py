import hashlib
import io
import tarfile
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_database_restorer import (
    InMemoryDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_database_snapshot import (
    InMemoryDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_reader import byte_chunks
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.domain.backup import BackupManifest, MediaFileRef, TableDigest
from app.modules.backup.domain.errors import (
    BackupNotFoundError,
    MediaFileMissingError,
    RestoreTargetNotEmptyError,
)
from app.modules.backup.domain.verification import (
    Finding,
    FindingKind,
    PruneReport,
    VerificationReport,
)
from app.modules.backup.ports.archive_member import ArchiveMember

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.ports.backup_reader import BackupReader
    from app.modules.backup.ports.backup_store import BackupStore
    from app.modules.backup.ports.backup_writer import BackupWriter
    from app.modules.backup.ports.database_restorer import DatabaseRestorer
    from app.modules.backup.ports.database_snapshot import DatabaseSnapshot
    from app.modules.backup.ports.media_files import MediaFiles


async def _failed_stream() -> AsyncIterator[bytes]:
    yield b"partial"
    raise OSError("stream failed")


async def test_archive_is_visible_only_after_finish() -> None:
    """The summary commits the archive; checksums describe uncompressed members."""
    store: BackupStore = InMemoryBackupStore()
    backup_id = uuid7()
    writer: BackupWriter = await store.begin(backup_id)
    data = b'{"id": "example"}\n'
    digest = await writer.add("data/users.ndjson", byte_chunks(data))
    assert (digest.size, digest.lines) == (len(data), 1)
    assert digest.sha256 == hashlib.sha256(data).hexdigest()
    assert await store.list() == []
    manifest = BackupManifest(
        app_version="1.0",
        alembic_revision="revision",
        label="manual",
        created_at=datetime.now(UTC),
        created_by=uuid7(),
        tables=[TableDigest(name="users", rows=1, sha256=digest.sha256)],
    )
    stored = await writer.finish(manifest)
    assert await store.list() == [stored.summary]
    raw = b"".join([chunk async for chunk in store.read_bytes(backup_id)])
    assert stored.summary.size == len(raw)
    assert stored.sha256 == hashlib.sha256(raw).hexdigest()
    assert await store.archive_digest(backup_id) == stored.sha256
    reader: BackupReader = await store.open(backup_id)
    contents = {
        member.name: b"".join([chunk async for chunk in member.chunks])
        async for member in reader.members()
    }
    assert list(contents) == ["data/users.ndjson", "checksums.sha256", "manifest.json"]
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        assert archive.getnames() == list(contents)
    for name in ("data/users.ndjson", "manifest.json"):
        expected = f"{hashlib.sha256(contents[name]).hexdigest()}  {name}\n".encode()
        assert expected in contents["checksums.sha256"]
    await writer.abort()
    assert await store.list() == [stored.summary]
    await store.delete(backup_id)
    assert await store.list() == []
    with pytest.raises(BackupNotFoundError):
        await store.open(backup_id)
    with pytest.raises(BackupNotFoundError):
        await store.delete(backup_id)


async def test_aborted_and_failed_writes_are_not_committed() -> None:
    """Partial uploads never acquire a summary."""
    store = InMemoryBackupStore()
    writer = await store.begin(uuid7())
    with pytest.raises(OSError, match="stream failed"):
        await writer.add("data/users.ndjson", _failed_stream())
    await writer.abort()
    assert await store.list() == []
    backup_id = uuid7()
    store.archives[backup_id] = b"orphan"
    assert await store.list() == []
    with pytest.raises(BackupNotFoundError):
        _ = [chunk async for chunk in store.read_bytes(backup_id)]
    with pytest.raises(BackupNotFoundError):
        await store.archive_digest(backup_id)


async def test_snapshot_and_atomic_restore() -> None:
    """The buffered restorer never publishes partially consumed tables."""
    snapshot: DatabaseSnapshot = InMemoryDatabaseSnapshot(
        "revision", {"data/users.ndjson": b"{}\n"}
    )
    target = InMemoryDatabaseRestorer("revision")
    restorer: DatabaseRestorer = target
    assert await snapshot.schema_revision() == await restorer.schema_revision()
    assert await restorer.is_empty()
    await restorer.restore_instance(snapshot.export(), replace=False, setup_only=True)
    assert target.tables == {"data/users.ndjson": b"{}\n"}
    assert not await restorer.is_empty()
    for replace, setup_only in ((False, False), (True, True)):
        with pytest.raises(RestoreTargetNotEmptyError):
            await restorer.restore_instance(
                snapshot.export(), replace=replace, setup_only=setup_only
            )

    async def failing_members() -> AsyncIterator[ArchiveMember]:
        yield ArchiveMember(name="data/users.ndjson", chunks=_failed_stream())

    with pytest.raises(OSError, match="stream failed"):
        await restorer.restore_instance(
            failing_members(), replace=True, setup_only=False
        )
    assert target.tables == {"data/users.ndjson": b"{}\n"}
    empty = InMemoryDatabaseSnapshot("revision", {})
    await restorer.restore_instance(empty.export(), replace=True, setup_only=False)
    assert await restorer.is_empty()


async def test_media_uses_status_buckets_and_keeps_missing_records() -> None:
    """Missing originals remain enumerable and rollback removes only bytes."""
    memory = InMemoryMediaFiles()
    media: MediaFiles = memory
    ref = MediaFileRef(
        asset_id=uuid7(),
        status="attached",
        size=3,
        sha256=hashlib.sha256(b"abc").hexdigest(),
    )
    await media.write(ref, byte_chunks(b"abc"))
    assert await media.list_files() == [ref]
    assert b"".join([chunk async for chunk in media.open(ref)]) == b"abc"
    with pytest.raises(OSError, match="stream failed"):
        await media.write(ref, _failed_stream())
    assert memory.files[(ref.asset_id, ref.status)] == b"abc"
    await media.remove(ref)
    await media.remove(ref)
    assert await media.list_files() == [ref]
    with pytest.raises(MediaFileMissingError):
        _ = [chunk async for chunk in media.open(ref)]


def test_verification_and_prune_reports_have_independent_findings() -> None:
    """Empty reports are clean and keep their own mutable collections."""
    report = VerificationReport()
    report.findings.append(Finding(kind=FindingKind.MISSING, member="manifest.json"))
    assert VerificationReport().findings == []
    prune = PruneReport()
    prune.kept.append("backup")
    assert PruneReport().kept == []

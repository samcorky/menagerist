import hashlib
import io
import tarfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid7

import pytest

from app.entrypoints.api.shared.authorisation import RoleAuthorisationAdapter
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_database_snapshot import (
    InMemoryDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_reader import byte_chunks
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.application.create_backup import (
    CreateBackup,
    CreateBackupCommand,
)
from app.modules.backup.application.delete_backup import (
    DeleteBackup,
    DeleteBackupCommand,
)
from app.modules.backup.application.list_backups import ListBackups, ListBackupsQuery
from app.modules.backup.application.open_backup import OpenBackup, OpenBackupQuery
from app.modules.backup.application.prune_backups import (
    PruneBackups,
    PruneBackupsCommand,
)
from app.modules.backup.application.verify_backup import VerifyBackup, VerifyBackupQuery
from app.modules.backup.domain.backup import MediaFileRef
from app.modules.backup.domain.errors import BackupNotFoundError, CorruptBackupError
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError, ValidationError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from app.modules.backup.domain.verification import FindingKind
from app.modules.backup.ports.archive_member import ArchiveMember


def _creator(
    store: InMemoryBackupStore, media: InMemoryMediaFiles | None = None
) -> CreateBackup:
    return CreateBackup(
        store,
        InMemoryDatabaseSnapshot("revision", {"data/users.ndjson": b"{}\n"}),
        media or InMemoryMediaFiles(),
        RoleAuthorisationAdapter(),
        app_version="1.0",
    )


async def test_create_verify_open_list_delete() -> None:
    """A completed instance archive is verified, listed and downloadable."""
    store = InMemoryBackupStore()
    summary = await _creator(store).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    auth = RoleAuthorisationAdapter()
    report = await VerifyBackup(store, auth).handle(
        VerifyBackupQuery(backup_id=summary.id), SYSTEM_ACTOR
    )
    assert report.findings == []
    assert await ListBackups(store, auth).handle(ListBackupsQuery(), SYSTEM_ACTOR) == [
        summary
    ]
    opened = await OpenBackup(store, auth).handle(
        OpenBackupQuery(backup_id=summary.id), SYSTEM_ACTOR
    )
    assert opened.summary == summary
    assert (
        b"".join([chunk async for chunk in opened.chunks]) == store.archives[summary.id]
    )
    await DeleteBackup(store, auth).handle(
        DeleteBackupCommand(backup_id=summary.id), SYSTEM_ACTOR
    )
    assert await store.list() == []
    with pytest.raises(BackupNotFoundError):
        await OpenBackup(store, auth).handle(
            OpenBackupQuery(backup_id=summary.id), SYSTEM_ACTOR
        )
    with pytest.raises(BackupNotFoundError):
        await DeleteBackup(store, auth).handle(
            DeleteBackupCommand(backup_id=summary.id), SYSTEM_ACTOR
        )


async def test_media_files_and_missing_originals() -> None:
    """All lifecycle buckets are archived; absent originals retain their records."""
    store = InMemoryBackupStore()
    media = InMemoryMediaFiles()
    for status in ("staged", "attached", "orphaned"):
        ref = MediaFileRef(
            asset_id=uuid7(),
            status=status,
            size=3,
            sha256=hashlib.sha256(b"abc").hexdigest(),
        )
        await media.write(ref, byte_chunks(b"abc"))
    missing = MediaFileRef(asset_id=uuid7(), status="attached", size=1, sha256="0" * 64)
    media.refs[missing.asset_id] = missing
    summary = await _creator(store, media).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    assert summary.size > 0
    assert len(await store.list()) == 1
    bad = replace(ref, sha256="0" * 64)
    media.refs[bad.asset_id] = bad
    with pytest.raises(CorruptBackupError):
        await _creator(store, media).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    assert len(await store.list()) == 1


async def test_verification_reports_missing_sidecar_and_corruption() -> None:
    """Digest failures are report data and never need an API exception handler."""
    store = InMemoryBackupStore()
    summary = await _creator(store).handle(
        CreateBackupCommand(verify=False), SYSTEM_ACTOR
    )
    del store.digests[summary.id]
    verifier = VerifyBackup(store, RoleAuthorisationAdapter())
    assert (
        await verifier.handle(VerifyBackupQuery(backup_id=summary.id), SYSTEM_ACTOR)
    ).findings
    store.digests[summary.id] = "0" * 64
    store.archives[summary.id] = b"broken archive"
    assert (
        await verifier.handle(VerifyBackupQuery(backup_id=summary.id), SYSTEM_ACTOR)
    ).findings


async def test_prune_keeps_group_floors_and_honours_age_and_dry_run() -> None:
    """Retention decisions use summary dates and keep migration backups separately."""
    store = InMemoryBackupStore()
    now = datetime.now(UTC)
    ids = []
    for label in ("manual", "manual", "manual", "pre-migration", "pre-migration"):
        summary = await _creator(store).handle(
            CreateBackupCommand(label=label, verify=False), SYSTEM_ACTOR
        )
        ids.append(summary.id)
        store.summaries[summary.id] = replace(
            summary, created_at=now - timedelta(days=20 - len(ids))
        )
    prune = PruneBackups(store, RoleAuthorisationAdapter())
    command = PruneBackupsCommand(
        keep_last=1, older_than=timedelta(days=7), pre_migration_keep=1, dry_run=True
    )
    report = await prune.handle(command, SYSTEM_ACTOR)
    assert set(report.deleted) == {str(ids[0]), str(ids[1]), str(ids[3])}
    assert len(await store.list()) == 5
    assert report.freed_bytes > 0
    result = await prune.handle(replace(command, dry_run=False), SYSTEM_ACTOR)
    assert result.deleted == report.deleted
    assert len(await store.list()) == 2
    assert (
        await prune.handle(
            PruneBackupsCommand(keep_last=0, pre_migration_keep=0), SYSTEM_ACTOR
        )
    ).deleted == []


async def test_prune_age_only_and_settings_defaults() -> None:
    """An age-only policy preserves the newest archive even with a zero floor."""
    store = InMemoryBackupStore()
    for _ in range(3):
        await _creator(store).handle(CreateBackupCommand(verify=False), SYSTEM_ACTOR)
    prune = PruneBackups(store, RoleAuthorisationAdapter(), keep_last=2)
    assert len((await prune.handle(PruneBackupsCommand(), SYSTEM_ACTOR)).deleted) == 1
    assert (
        await prune.handle(
            PruneBackupsCommand(older_than=timedelta(days=1)), SYSTEM_ACTOR
        )
    ).deleted == []
    assert (
        len(
            (
                await prune.handle(
                    PruneBackupsCommand(older_than=timedelta(0)), SYSTEM_ACTOR
                )
            ).deleted
        )
        == 1
    )


@pytest.mark.parametrize(
    "command",
    [
        PruneBackupsCommand(keep_last=-1),
        PruneBackupsCommand(pre_migration_keep=-1),
        PruneBackupsCommand(older_than=timedelta(days=-1)),
    ],
)
async def test_prune_rejects_negative_limits(command: PruneBackupsCommand) -> None:
    """Invalid limits cannot delete backups."""
    with pytest.raises(ValidationError):
        await PruneBackups(InMemoryBackupStore(), RoleAuthorisationAdapter()).handle(
            command, SYSTEM_ACTOR
        )


async def test_member_cannot_access_instance_archives() -> None:
    """Permission checks run before any backup content is read or created."""
    actor = Actor(id=uuid7(), roles=frozenset({"member"}))
    with pytest.raises(ForbiddenError):
        await _creator(InMemoryBackupStore()).handle(CreateBackupCommand(), actor)


async def test_failed_post_write_verification_removes_archive() -> None:
    """A completed but unverified archive never remains listed as a good backup."""

    class WrongDigestStore(InMemoryBackupStore):
        async def archive_digest(self, backup_id: UUID) -> str:
            return "0" * 64

    store = WrongDigestStore()
    with pytest.raises(CorruptBackupError, match="failed integrity"):
        await _creator(store).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    assert await store.list() == []
    assert store.archives == {}


async def test_failed_export_closes_snapshot_and_discards_partial_archive() -> None:
    """Write failures release the snapshot transaction before returning."""

    class FailedSnapshot(InMemoryDatabaseSnapshot):
        closed = False

        async def export(self) -> AsyncGenerator[ArchiveMember]:
            try:
                yield ArchiveMember(name="data/users.ndjson", chunks=failed_chunks())
            finally:
                self.closed = True

    async def failed_chunks() -> AsyncGenerator[bytes]:
        yield b"partial"
        raise OSError("failed read")

    snapshot = FailedSnapshot("revision", {})
    store = InMemoryBackupStore()
    creator = CreateBackup(
        store,
        snapshot,
        InMemoryMediaFiles(),
        RoleAuthorisationAdapter(),
        app_version="1.0",
    )
    with pytest.raises(OSError, match="failed read"):
        await creator.handle(CreateBackupCommand(), SYSTEM_ACTOR)
    assert snapshot.closed
    assert await store.list() == []


async def test_open_finds_backup_among_other_summaries() -> None:
    """Downloading an older or later entry does not depend on list position."""
    store = InMemoryBackupStore()
    first = await _creator(store).handle(
        CreateBackupCommand(verify=False), SYSTEM_ACTOR
    )
    second = await _creator(store).handle(
        CreateBackupCommand(verify=False), SYSTEM_ACTOR
    )
    opened = await OpenBackup(store, RoleAuthorisationAdapter()).handle(
        OpenBackupQuery(backup_id=second.id), SYSTEM_ACTOR
    )
    assert opened.summary == second
    summaries = await ListBackups(store, RoleAuthorisationAdapter()).handle(
        ListBackupsQuery(), SYSTEM_ACTOR
    )
    assert summaries == [second, first]


async def test_duplicate_members_and_metadata_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated names and oversized metadata are findings, with the stream closed."""
    import app.modules.backup.application.verify_backup as verification

    store = InMemoryBackupStore()
    summary = await _creator(store).handle(
        CreateBackupCommand(verify=False), SYSTEM_ACTOR
    )
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in [
            *store.members[summary.id].items(),
            ("data/users.ndjson", b"{}\n"),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    store.archives[summary.id] = buffer.getvalue()
    store.digests[summary.id] = hashlib.sha256(buffer.getvalue()).hexdigest()
    verifier = VerifyBackup(store, RoleAuthorisationAdapter())
    report = await verifier.handle(
        VerifyBackupQuery(backup_id=summary.id), SYSTEM_ACTOR
    )
    assert any(
        f.kind == FindingKind.UNEXPECTED and f.actual == "duplicate member"
        for f in report.findings
    )
    monkeypatch.setattr(verification, "_METADATA_LIMIT", 8)
    report = await verifier.handle(
        VerifyBackupQuery(backup_id=summary.id), SYSTEM_ACTOR
    )
    assert any(
        f.kind == FindingKind.MANIFEST_INVALID
        and "metadata exceeds" in (f.actual or "")
        for f in report.findings
    )


async def test_digest_read_failure_is_a_verification_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed compressed digest read is report data rather than a raised error."""
    from app.modules.backup.adapters.storage.local_backup_reader import (
        LocalBackupReader,
    )

    async def failed_digest(self: LocalBackupReader) -> str:
        raise CorruptBackupError("Digest unavailable")

    store = InMemoryBackupStore()
    summary = await _creator(store).handle(
        CreateBackupCommand(verify=False), SYSTEM_ACTOR
    )
    monkeypatch.setattr(LocalBackupReader, "archive_digest", failed_digest)
    report = await VerifyBackup(store, RoleAuthorisationAdapter()).handle(
        VerifyBackupQuery(backup_id=summary.id), SYSTEM_ACTOR
    )
    assert any(
        f.kind == FindingKind.MANIFEST_INVALID and f.actual == "Digest unavailable"
        for f in report.findings
    )

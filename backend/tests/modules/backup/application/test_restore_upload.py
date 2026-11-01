import hashlib
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_database_restorer import (
    InMemoryDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_database_snapshot import (
    InMemoryDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.adapters.storage.in_memory_backup_workspace import (
    InMemoryBackupWorkspace,
)
from app.modules.backup.application.create_backup import (
    CreateBackup,
    CreateBackupCommand,
)
from app.modules.backup.application.restore_backup import (
    RestoreBackup,
    RestoreBackupCommand,
    archive_manifest,
    restore_verified_backup,
    transactional_media_members,
)
from app.modules.backup.application.upload_backup import (
    UploadBackup,
    UploadBackupCommand,
    upload_verified_backup,
)
from app.modules.backup.domain.backup import (
    BackupManifest,
    BackupScope,
    BackupSummary,
    MediaFileRef,
)
from app.modules.backup.domain.errors import (
    CorruptBackupError,
    IncompatibleBackupError,
    RestoreTargetNotEmptyError,
)
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from app.modules.backup.adapters.storage.in_memory_backup_writer import (
        InMemoryBackupWriter,
    )
    from app.modules.backup.adapters.storage.local_backup_reader import (
        LocalBackupReader,
    )


async def chunks(data: bytes) -> AsyncIterator[bytes]:
    """Yield test bytes."""
    yield data


async def archive() -> tuple[InMemoryBackupStore, BackupSummary, MediaFileRef]:
    """Create a verified archive with one original."""
    store = InMemoryBackupStore()
    media = InMemoryMediaFiles()
    ref = MediaFileRef(
        asset_id=uuid7(),
        status="attached",
        size=3,
        sha256=hashlib.sha256(b"new").hexdigest(),
    )
    await media.write(ref, chunks(b"new"))
    summary = await CreateBackup(
        store,
        InMemoryDatabaseSnapshot("rev", {"data/users.ndjson": b"{}\n"}),
        media,
        get_access_guard(),
        app_version="1",
    ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    return store, summary, ref


def test_restore_defaults() -> None:
    """Exercise archive integrity and transactional restoration."""
    command = RestoreBackupCommand(backup_id=uuid7())
    assert not command.replace
    assert not command.setup_only


def test_upload_command() -> None:
    """Exercise archive integrity and transactional restoration."""
    stream = chunks(b"archive")
    assert UploadBackupCommand(stream=stream).stream is stream


async def test_upload_and_restore_round_trip() -> None:
    """Exercise archive integrity and transactional restoration."""
    source, summary, ref = await archive()
    store, workspace, media = (
        InMemoryBackupStore(),
        InMemoryBackupWorkspace(),
        InMemoryMediaFiles(),
    )
    uploaded = await UploadBackup(store, workspace, get_access_guard()).handle(
        UploadBackupCommand(stream=source.read_bytes(summary.id)), SYSTEM_ACTOR
    )
    target = InMemoryDatabaseRestorer("rev")
    await RestoreBackup(store, target, media, workspace, get_access_guard()).handle(
        RestoreBackupCommand(backup_id=uploaded.id), SYSTEM_ACTOR
    )
    assert target.tables == {"data/users.ndjson": b"{}\n"}
    assert media.files[(ref.asset_id, ref.status)] == b"new"
    assert not workspace.files


async def test_restore_rejects_revision_nonempty_and_tampering() -> None:
    """Exercise archive integrity and transactional restoration."""
    store, summary, _ = await archive()
    workspace, media = InMemoryBackupWorkspace(), InMemoryMediaFiles()
    with pytest.raises(IncompatibleBackupError):
        await restore_verified_backup(
            store, InMemoryDatabaseRestorer("other"), media, workspace, summary.id
        )
    target = InMemoryDatabaseRestorer("rev")
    target.tables = {"data/users.ndjson": b"old"}
    with pytest.raises(RestoreTargetNotEmptyError):
        await restore_verified_backup(store, target, media, workspace, summary.id)
    store.digests[summary.id] = "0" * 64
    with pytest.raises(CorruptBackupError):
        await restore_verified_backup(store, target, media, workspace, summary.id)


@pytest.mark.parametrize("preexisting", [True, False])
async def test_restore_rolls_back_overwritten_originals(preexisting: bool) -> None:
    """Exercise archive integrity and transactional restoration."""
    store, summary, ref = await archive()
    workspace = InMemoryBackupWorkspace()

    class FailingMedia(InMemoryMediaFiles):
        async def write(self, ref: MediaFileRef, stream: AsyncIterator[bytes]) -> None:
            """Fail after writing the imported bytes."""
            await super().write(ref, stream)
            if self.files[(ref.asset_id, ref.status)] == b"new":
                raise OSError("disk failed")

    media = FailingMedia()
    if preexisting:
        await media.write(replace(ref, size=3), chunks(b"old"))
    target = InMemoryDatabaseRestorer("rev")
    with pytest.raises(OSError, match="disk failed"):
        await restore_verified_backup(
            store, target, media, workspace, summary.id, replace=True
        )
    assert not target.tables
    assert media.files.get((ref.asset_id, ref.status)) == (
        b"old" if preexisting else None
    )
    assert not workspace.files


async def test_upload_rejects_corrupt_oversize_and_scope() -> None:
    """Exercise archive integrity and transactional restoration."""
    store, workspace = InMemoryBackupStore(), InMemoryBackupWorkspace()
    for data, cap in [(b"bad", 100), (b"too big", 1)]:
        with pytest.raises(CorruptBackupError):
            await upload_verified_backup(store, workspace, chunks(data), cap)
    source, summary, _ = await archive()
    with pytest.raises(IncompatibleBackupError):
        await upload_verified_backup(
            store,
            workspace,
            source.read_bytes(summary.id),
            100000,
            allowed_scope=BackupScope.USER,
        )
    assert not store.archives
    assert not workspace.files


async def test_restore_refuses_user_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject a verified archive with the wrong restore scope."""
    store, summary, _ = await archive()
    manifest = await archive_manifest(store, summary.id)

    async def user_manifest(store: object, backup_id: object) -> BackupManifest:
        return replace(manifest, scope=BackupScope.USER)

    monkeypatch.setattr(
        "app.modules.backup.application.restore_backup.archive_manifest", user_manifest
    )
    with pytest.raises(IncompatibleBackupError):
        await restore_verified_backup(
            store,
            InMemoryDatabaseRestorer("rev"),
            InMemoryMediaFiles(),
            InMemoryBackupWorkspace(),
            summary.id,
        )


async def test_upload_aborts_failed_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An output failure discards both private and writer staging."""
    source, summary, _ = await archive()
    store, workspace = InMemoryBackupStore(), InMemoryBackupWorkspace()
    writer = await store.begin(uuid7())

    async def fail(*args: object) -> None:
        raise OSError("output failed")

    async def begin(backup_id: object) -> InMemoryBackupWriter:
        return writer

    monkeypatch.setattr(writer, "finish", fail)
    monkeypatch.setattr(store, "begin", begin)
    with pytest.raises(OSError, match="output failed"):
        await upload_verified_backup(
            store, workspace, source.read_bytes(summary.id), 100000
        )
    assert not workspace.files
    assert not store.archives


@pytest.mark.parametrize("changed_open", [2, 3])
async def test_restore_rolls_back_archive_changed_after_verification(
    monkeypatch: pytest.MonkeyPatch,
    changed_open: int,
) -> None:
    """A file replaced on the restore pass cannot commit unverified rows or media."""
    store, summary, ref = await archive()
    original_open = store.open
    open_count = 0
    altered = InMemoryBackupStore()
    writer = await altered.begin(summary.id)
    await writer.add("data/users.ndjson", chunks(b'{"altered": true}\n'))
    await writer.add(f"media/{ref.asset_id}", chunks(b"new"))
    await writer.finish(await archive_manifest(store, summary.id))

    async def changing_open(backup_id: UUID) -> LocalBackupReader:
        nonlocal open_count
        open_count += 1
        if open_count == changed_open:
            store.archives[backup_id] = altered.archives[backup_id]
        return await original_open(backup_id)

    monkeypatch.setattr(store, "open", changing_open)
    target, media, workspace = (
        InMemoryDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
    )
    await media.write(ref, chunks(b"old"))
    with pytest.raises(CorruptBackupError, match="changed after"):
        await restore_verified_backup(store, target, media, workspace, summary.id)
    assert not target.tables
    assert media.files[(ref.asset_id, ref.status)] == b"old"
    assert not workspace.files


async def test_media_iterator_without_digest_constraint() -> None:
    """The reusable iterator also supports callers without a pinned archive digest."""
    store, summary, ref = await archive()
    media, workspace = InMemoryMediaFiles(), InMemoryBackupWorkspace()
    manifest = await archive_manifest(store, summary.id)
    async for member in transactional_media_members(
        await store.open(summary.id), manifest, media, workspace, []
    ):
        async for _ in member.chunks:
            pass
    assert media.files[(ref.asset_id, ref.status)] == b"new"

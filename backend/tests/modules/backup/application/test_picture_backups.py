"""Account pictures travel in instance backups alongside media originals."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.media.in_memory_picture_files import (
    InMemoryPictureFiles,
)
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
from app.modules.backup.application.archive import (
    analyse_members,
    checksum_bytes,
    manifest_bytes,
    parse_manifest,
    validate_member_name,
)
from app.modules.backup.application.create_backup import (
    CreateBackup,
    CreateBackupCommand,
)
from app.modules.backup.application.restore_backup import restore_verified_backup
from app.modules.backup.domain.backup import (
    BackupManifest,
    MemberDigest,
    PictureFileRef,
)
from app.modules.backup.domain.errors import CorruptBackupError
from app.modules.backup.domain.verification import FindingKind
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.domain.backup import BackupSummary

USER = uuid7()


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _ref(data: bytes = b"cat", *, pixels: int = 64) -> PictureFileRef:
    return PictureFileRef(
        user_id=USER,
        version="0123456789abcdef",
        pixels=pixels,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _digest(data: bytes) -> MemberDigest:
    return MemberDigest(
        size=len(data), sha256=hashlib.sha256(data).hexdigest(), lines=data.count(b"\n")
    )


def _manifest(**changes: object) -> BackupManifest:
    manifest = BackupManifest(
        app_version="1.0",
        alembic_revision="rev",
        label="manual",
        created_at=datetime.now(UTC),
        created_by=uuid7(),
    )
    return replace(manifest, **changes)  # type: ignore[arg-type]


async def _backup(
    pictures: InMemoryPictureFiles,
) -> tuple[InMemoryBackupStore, BackupSummary]:
    store = InMemoryBackupStore()
    summary = await CreateBackup(
        store,
        InMemoryDatabaseSnapshot("rev", {"data/users.ndjson": b"{}\n"}),
        InMemoryMediaFiles(),
        get_access_guard(),
        app_version="1",
        pictures=pictures,
    ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    return store, summary


def test_picture_member_names_are_safe() -> None:
    """A picture lives at `avatars/<user id>/<version>-<size>.webp` and nowhere else."""
    validate_member_name(f"avatars/{USER}/0123456789abcdef-64.webp")
    assert _ref().member == f"avatars/{USER}/0123456789abcdef-64.webp"
    for bad in (
        f"avatars/{USER}/../x-64.webp",
        f"avatars/{USER}/0123456789ABCDEF-64.webp",
        f"avatars/{USER}/0123456789abcdef-99.webp",
        f"avatars/{USER}/0123456789abcdef-64.png",
        "avatars/not-a-user/0123456789abcdef-64.webp",
        f"avatars/{USER}",
        # Looks like a UUID to the pattern, but is not one in canonical form.
        "avatars/0123456789abcdef0123456789abcdef----/0123456789abcdef-64.webp",
        f"avatars/{'-' * 36}/0123456789abcdef-64.webp",
    ):
        with pytest.raises(CorruptBackupError):
            validate_member_name(bad)


def test_manifest_round_trip_with_pictures() -> None:
    """Pictures are recorded in the manifest and read back unchanged."""
    manifest = _manifest(pictures=[_ref()])
    assert parse_manifest(manifest_bytes(manifest)) == manifest


def test_archives_from_before_pictures_still_parse() -> None:
    """A manifest with no pictures list is an older archive with no pictures."""
    payload = json.loads(manifest_bytes(_manifest()))
    del payload["pictures"]
    assert parse_manifest(json.dumps(payload).encode()).pictures == []


def test_duplicate_or_unsafe_picture_records_are_corrupt() -> None:
    """A manifest naming one file twice, or an impossible one, is refused."""
    with pytest.raises(CorruptBackupError):
        parse_manifest(manifest_bytes(_manifest(pictures=[_ref(), _ref()])))
    with pytest.raises(CorruptBackupError):
        parse_manifest(manifest_bytes(_manifest(pictures=[replace(_ref(), pixels=99)])))
    with pytest.raises(CorruptBackupError):
        parse_manifest(
            manifest_bytes(_manifest(pictures=[replace(_ref(), version="x")]))
        )


def test_verification_checks_picture_members() -> None:
    """A missing picture, or one of the wrong size, is a finding."""
    ref = _ref(b"cat")
    encoded = manifest_bytes(_manifest(pictures=[ref]))
    missing = {"manifest.json": _digest(encoded)}
    report = analyse_members(missing, encoded, checksum_bytes(missing))
    assert any(
        f.member == ref.member and f.kind == FindingKind.MISSING
        for f in report.findings
    )
    wrong = {"manifest.json": _digest(encoded), ref.member: _digest(b"dog!")}
    report = analyse_members(wrong, encoded, checksum_bytes(wrong))
    assert any(f.kind == FindingKind.MEDIA_MISMATCH for f in report.findings)


async def test_backup_carries_pictures_and_restore_writes_them() -> None:
    """Restoring onto a fresh host brings every picture back."""
    source = InMemoryPictureFiles()
    await source.write(_ref(b"cat"), _chunks(b"cat"))
    await source.write(_ref(b"kitten", pixels=128), _chunks(b"kitten"))
    store, summary = await _backup(source)

    target = InMemoryPictureFiles()
    await restore_verified_backup(
        store,
        InMemoryDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        summary.id,
        pictures=target,
    )

    assert target.files == source.files


async def test_backup_without_a_picture_source_records_none() -> None:
    """Callers that pass no picture source keep the old behaviour."""
    store, summary = await _backup(InMemoryPictureFiles())
    target = InMemoryPictureFiles()
    await restore_verified_backup(
        store,
        InMemoryDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        summary.id,
    )
    assert target.files == {}


@pytest.mark.parametrize("preexisting", [True, False])
async def test_failed_restore_puts_pictures_back(preexisting: bool) -> None:
    """A restore that fails leaves pictures exactly as they were."""
    source = InMemoryPictureFiles()
    await source.write(_ref(b"new"), _chunks(b"new"))
    store, summary = await _backup(source)

    class FailingRestorer(InMemoryDatabaseRestorer):
        async def restore_instance(self, *args: object, **kwargs: object) -> None:
            """Consume the archive, then fail as a database would at commit."""
            await super().restore_instance(*args, **kwargs)  # type: ignore[arg-type]
            raise OSError("database failed")

    target = InMemoryPictureFiles()
    if preexisting:
        await target.write(_ref(b"old"), _chunks(b"old"))
    workspace = InMemoryBackupWorkspace()
    with pytest.raises(OSError, match="database failed"):
        await restore_verified_backup(
            store,
            FailingRestorer("rev"),
            InMemoryMediaFiles(),
            workspace,
            summary.id,
            replace=True,
            pictures=target,
        )

    key = (USER, "0123456789abcdef", 64)
    assert target.files.get(key) == (b"old" if preexisting else None)
    assert not workspace.files


async def test_a_picture_that_vanishes_during_the_backup_is_left_out() -> None:
    """A picture replaced while the backup runs is skipped, not an error."""

    class Vanishing(InMemoryPictureFiles):
        async def list_files(self) -> list[PictureFileRef]:
            """List one more file than is really there."""
            return [*await super().list_files(), _ref(b"gone", pixels=256)]

    pictures = Vanishing()
    await pictures.write(_ref(b"cat"), _chunks(b"cat"))
    store, summary = await _backup(pictures)
    target = InMemoryPictureFiles()
    await restore_verified_backup(
        store,
        InMemoryDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        summary.id,
        pictures=target,
    )
    assert list(target.files) == [(USER, "0123456789abcdef", 64)]


async def test_a_picture_that_changes_during_the_backup_fails_it() -> None:
    """Bytes that no longer match what was listed make the backup fail, not lie."""

    class Changing(InMemoryPictureFiles):
        async def list_files(self) -> list[PictureFileRef]:
            """Describe the file with a hash it does not have."""
            return [replace(ref, sha256="0" * 64) for ref in await super().list_files()]

    pictures = Changing()
    await pictures.write(_ref(b"cat"), _chunks(b"cat"))
    with pytest.raises(CorruptBackupError):
        await _backup(pictures)


async def test_replacing_restore_drops_pictures_the_archive_does_not_have() -> None:
    """After a restore, only the archive's pictures remain; others would be strays."""
    source = InMemoryPictureFiles()
    await source.write(_ref(b"cat"), _chunks(b"cat"))
    store, summary = await _backup(source)

    target = InMemoryPictureFiles()
    stray = replace(_ref(b"old"), user_id=uuid7())
    await target.write(stray, _chunks(b"old"))
    await restore_verified_backup(
        store,
        InMemoryDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        summary.id,
        replace=True,
        pictures=target,
    )

    assert target.files == source.files


async def test_a_stuck_stray_picture_does_not_fail_the_restore() -> None:
    """The restore has committed; a file that cannot be removed is only logged."""
    store, summary = await _backup(InMemoryPictureFiles())

    class Stuck(InMemoryPictureFiles):
        async def remove(self, ref: PictureFileRef) -> None:
            """Fail as a file in use would."""
            raise PermissionError("in use")

    target = Stuck()
    await target.write(_ref(b"old"), _chunks(b"old"))
    await restore_verified_backup(
        store,
        InMemoryDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        summary.id,
        replace=True,
        pictures=target,
    )
    assert len(target.files) == 1

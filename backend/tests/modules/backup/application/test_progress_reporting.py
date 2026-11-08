"""Backup, restore and user transfer report against their phase plans."""

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_database_restorer import (
    InMemoryDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_database_snapshot import (
    InMemoryDatabaseSnapshot,
)
from app.modules.backup.adapters.persistence.in_memory_setup_gate import (
    InMemorySetupGate,
)
from app.modules.backup.adapters.persistence.in_memory_user_database_restorer import (
    InMemoryUserDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_user_database_snapshot import (
    InMemoryUserDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.adapters.storage.in_memory_backup_workspace import (
    InMemoryBackupWorkspace,
)
from app.modules.backup.application.create_backup import (
    CREATE_PLAN,
    VERIFY_PHASE,
    CreateBackup,
    CreateBackupCommand,
)
from app.modules.backup.application.export_user_data import (
    EXPORT_PLAN,
    ExportUserData,
    ExportUserDataCommand,
)
from app.modules.backup.application.import_user_data import (
    IMPORT_PLAN,
    ImportUserData,
    ImportUserDataCommand,
)
from app.modules.backup.application.restore_backup import (
    RESTORE_PLAN,
    RestoreBackup,
    RestoreBackupCommand,
)
from app.modules.backup.application.restore_on_first_run import (
    RestoreOnFirstRun,
    RestoreOnFirstRunCommand,
)
from app.modules.backup.application.verify_backup import (
    VERIFY_PLAN,
    VerifyBackup,
    VerifyBackupQuery,
)
from app.modules.backup.domain.backup import MediaFileRef
from app.modules.backup.domain.errors import CorruptBackupError
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR, Actor
from app.shared_kernel.progress import RecordingProgress

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass
class PhaseLog:
    """What one phase was told: its total and the units advanced against it."""

    total: int | None
    advanced: int = 0


def phases(progress: RecordingProgress) -> dict[str, PhaseLog]:
    """Fold the recorded calls into one `PhaseLog` per started phase."""
    log: dict[str, PhaseLog] = {}
    current: PhaseLog | None = None
    for call in progress.calls:
        if call[0] == "start":
            current = log[str(call[1])] = PhaseLog(total=call[2])  # type: ignore[arg-type]
        elif call[0] == "advance":
            assert current is not None
            current.advanced += call[1]  # type: ignore[operator]
    return log


def started(progress: RecordingProgress) -> list[str]:
    """The phase keys, in the order they were started."""
    return [str(call[1]) for call in progress.calls if call[0] == "start"]


async def chunks(data: bytes) -> AsyncIterator[bytes]:
    """Yield test bytes."""
    yield data


def media_ref(data: bytes) -> MediaFileRef:
    """A media original's manifest record."""
    return MediaFileRef(
        asset_id=uuid7(),
        status="attached",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


async def instance_archive(
    *, files: int = 2, rows: int = 3, progress: RecordingProgress | None = None
) -> tuple[InMemoryBackupStore, UUID, int]:
    """Create an instance backup with `files` originals and `rows` user rows."""
    media = InMemoryMediaFiles()
    for index in range(files):
        data = f"file-{index}".encode()
        ref = media_ref(data)
        await media.write(ref, chunks(data))
    store = InMemoryBackupStore()
    summary = await CreateBackup(
        store,
        InMemoryDatabaseSnapshot("rev", {"data/users.ndjson": b"{}\n" * rows}),
        media,
        get_access_guard(),
        app_version="test",
        progress=progress,
    ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    return store, summary.id, summary.size


# --- CreateBackup -------------------------------------------------------------


async def test_create_backup_reports_every_phase_and_ends_done() -> None:
    """Create reports the plan, one unit per file, the verify bytes, then done."""
    progress = RecordingProgress()
    _, _, size = await instance_archive(files=2, progress=progress)
    assert progress.calls[0] == ("begin", (*CREATE_PLAN, VERIFY_PHASE))
    assert progress.calls[-1] == ("done",)
    assert started(progress) == ["database", "media", "verify"]
    log = phases(progress)
    assert (log["media"].total, log["media"].advanced) == (2, 2)
    assert (log["verify"].total, log["verify"].advanced) == (size, size)


async def test_create_backup_counts_a_missing_original_as_handled() -> None:
    """A file that has vanished still moves the media phase on."""
    media = InMemoryMediaFiles()
    ref = media_ref(b"gone")
    media.refs[ref.asset_id] = ref  # listed, but with no file behind it
    progress = RecordingProgress()
    await CreateBackup(
        InMemoryBackupStore(),
        InMemoryDatabaseSnapshot("rev", {"data/users.ndjson": b"{}\n"}),
        media,
        get_access_guard(),
        app_version="test",
        progress=progress,
    ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    assert phases(progress)["media"].advanced == 1


async def test_create_backup_without_verification_has_no_verify_phase() -> None:
    """Skipping the post-write check drops its phase from the plan."""
    progress = RecordingProgress()
    await CreateBackup(
        InMemoryBackupStore(),
        InMemoryDatabaseSnapshot("rev", {"data/users.ndjson": b"{}\n"}),
        InMemoryMediaFiles(),
        get_access_guard(),
        app_version="test",
        progress=progress,
    ).handle(CreateBackupCommand(verify=False), SYSTEM_ACTOR)
    assert progress.calls[0] == ("begin", CREATE_PLAN)
    assert started(progress) == ["database", "media"]


async def test_create_backup_leaves_failure_to_the_reporter_owner() -> None:
    """A failed verification propagates and is not reported as done."""

    class WrongDigestStore(InMemoryBackupStore):
        async def archive_digest(self, backup_id: UUID) -> str:
            """Never match the real digest."""
            return "0" * 64

    progress = RecordingProgress()
    with pytest.raises(CorruptBackupError):
        await CreateBackup(
            WrongDigestStore(),
            InMemoryDatabaseSnapshot("rev", {"data/users.ndjson": b"{}\n"}),
            InMemoryMediaFiles(),
            get_access_guard(),
            app_version="test",
            progress=progress,
        ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    assert ("done",) not in progress.calls


# --- VerifyBackup ---------------------------------------------------------------


async def test_verify_backup_reports_the_compressed_bytes_it_reads() -> None:
    """One pass over the archive, sized by its compressed length."""
    store, backup_id, size = await instance_archive(files=1)
    progress = RecordingProgress()
    report = await VerifyBackup(store, get_access_guard(), progress=progress).handle(
        VerifyBackupQuery(backup_id=backup_id), SYSTEM_ACTOR
    )
    assert report.findings == []
    assert progress.calls[0] == ("begin", VERIFY_PLAN)
    assert progress.calls[-1] == ("done",)
    log = phases(progress)
    assert (log["verify"].total, log["verify"].advanced) == (size, size)


# --- RestoreBackup and RestoreOnFirstRun ----------------------------------------


async def test_restore_reports_verify_bytes_rows_and_files() -> None:
    """Restore reads the archive twice to verify, then counts rows and files."""
    store, backup_id, size = await instance_archive(files=2, rows=3)
    progress = RecordingProgress()
    await RestoreBackup(
        store,
        InMemoryDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        get_access_guard(),
        progress=progress,
    ).handle(RestoreBackupCommand(backup_id=backup_id), SYSTEM_ACTOR)
    assert progress.calls[0] == ("begin", RESTORE_PLAN)
    assert progress.calls[-1] == ("done",)
    assert started(progress) == ["verify", "database", "media"]
    log = phases(progress)
    assert (log["verify"].total, log["verify"].advanced) == (2 * size, 2 * size)
    assert (log["database"].total, log["database"].advanced) == (3, 3)
    assert (log["media"].total, log["media"].advanced) == (2, 2)


async def test_restore_without_media_never_starts_the_media_phase() -> None:
    """An archive with no originals leaves the media phase to `done()`."""
    store, backup_id, _ = await instance_archive(files=0)
    progress = RecordingProgress()
    await RestoreBackup(
        store,
        InMemoryDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        get_access_guard(),
        progress=progress,
    ).handle(RestoreBackupCommand(backup_id=backup_id), SYSTEM_ACTOR)
    assert started(progress) == ["verify", "database"]


async def test_first_run_restore_reports_through_the_same_plan() -> None:
    """The anonymous setup path hands its reporter to the shared restore."""
    source, backup_id, _ = await instance_archive(files=1)
    archive = b"".join([chunk async for chunk in source.read_bytes(backup_id)])
    progress = RecordingProgress()
    await RestoreOnFirstRun(
        InMemorySetupGate(),
        InMemoryBackupStore(),
        InMemoryDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        get_access_guard(),
        progress=progress,
    ).handle(RestoreOnFirstRunCommand(stream=chunks(archive)), ANONYMOUS_ACTOR)
    assert progress.calls[0] == ("begin", RESTORE_PLAN)
    assert started(progress) == ["verify", "database", "media"]
    assert progress.calls[-1] == ("done",)


# --- ExportUserData and ImportUserData -------------------------------------------


async def export_user(
    progress: RecordingProgress | None = None,
) -> tuple[InMemoryBackupStore, UUID, int, Actor]:
    """Export one person's single item and one original."""
    actor = Actor(id=uuid7())
    item_id, asset_id = uuid7(), uuid7()
    media = InMemoryMediaFiles()
    ref = MediaFileRef(
        asset_id=asset_id,
        status="attached",
        size=4,
        sha256=hashlib.sha256(b"data").hexdigest(),
    )
    media.refs[asset_id] = ref
    media.files[(asset_id, "attached")] = b"data"
    tables: dict[str, list[dict[str, object]]] = {
        "nodes": [{"id": item_id, "owner_id": actor.id, "name": "Mine", "type": "t"}],
        "node_types": [{"id": uuid7(), "slug": "t", "attributes_schema": None}],
        "media_assets": [
            {
                "id": asset_id,
                "owner_id": actor.id,
                "status": "attached",
                "size": 4,
                "sha256": ref.sha256,
            }
        ],
    }
    store = InMemoryBackupStore()
    summary = await ExportUserData(
        store,
        InMemoryUserDatabaseSnapshot("rev", tables),
        media,
        InMemoryAccessGuard(),
        app_version="test",
        progress=progress,
    ).handle(ExportUserDataCommand(), actor)
    return store, summary.id, summary.size, actor


async def test_export_user_data_reports_every_phase_and_ends_done() -> None:
    """Export counts its originals and verifies the finished archive."""
    progress = RecordingProgress()
    _, _, size, _ = await export_user(progress)
    assert progress.calls[0] == ("begin", EXPORT_PLAN)
    assert progress.calls[-1] == ("done",)
    assert started(progress) == ["database", "media", "verify"]
    log = phases(progress)
    assert (log["media"].total, log["media"].advanced) == (1, 1)
    assert (log["verify"].total, log["verify"].advanced) == (size, size)


async def test_import_user_data_reports_three_verify_passes_rows_and_files() -> None:
    """Import reads the archive three times before it writes anything."""
    store, backup_id, size, _ = await export_user()
    progress = RecordingProgress()
    await ImportUserData(
        store,
        InMemoryUserDatabaseRestorer("rev"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        InMemoryAccessGuard(),
        progress=progress,
    ).handle(ImportUserDataCommand(backup_id=backup_id), Actor(id=uuid7()))
    assert progress.calls[0] == ("begin", IMPORT_PLAN)
    assert progress.calls[-1] == ("done",)
    assert started(progress) == ["verify", "database", "media"]
    log = phases(progress)
    assert (log["verify"].total, log["verify"].advanced) == (3 * size, 3 * size)
    assert log["database"].advanced == log["database"].total
    assert (log["media"].total, log["media"].advanced) == (1, 1)

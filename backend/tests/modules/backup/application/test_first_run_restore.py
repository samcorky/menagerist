from typing import TYPE_CHECKING

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
from app.modules.backup.application.restore_on_first_run import (
    RestoreOnFirstRun,
    RestoreOnFirstRunCommand,
)
from app.modules.backup.domain.errors import (
    CorruptBackupError,
    RestoreTargetNotEmptyError,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _archive() -> bytes:
    store = InMemoryBackupStore()
    summary = await CreateBackup(
        store,
        InMemoryDatabaseSnapshot(
            "revision", {"data/users.ndjson": b'{"id":"admin"}\n'}
        ),
        InMemoryMediaFiles(),
        get_access_guard(),
        app_version="test",
    ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    return b"".join([chunk async for chunk in store.read_bytes(summary.id)])


async def _chunks(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def test_first_run_restores_accounts_and_removes_temporary_upload() -> None:
    """The anonymous setup path restores without creating a new administrator."""
    store = InMemoryBackupStore()
    target = InMemoryDatabaseRestorer("revision")
    use_case = RestoreOnFirstRun(
        InMemorySetupGate(),
        store,
        target,
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        get_access_guard(),
    )
    await use_case.handle(
        RestoreOnFirstRunCommand(stream=_chunks(await _archive())), ANONYMOUS_ACTOR
    )
    assert target.tables == {"data/users.ndjson": b'{"id":"admin"}\n'}
    assert await store.list() == []
    with pytest.raises(RestoreTargetNotEmptyError):
        await use_case.handle(
            RestoreOnFirstRunCommand(stream=_chunks(await _archive())), ANONYMOUS_ACTOR
        )
    assert await store.list() == []


async def test_closed_setup_does_not_read_upload() -> None:
    """Existing accounts refuse public restoration before consuming any body bytes."""

    async def unreadable() -> AsyncIterator[bytes]:
        raise AssertionError("The upload must not be read.")
        yield b""  # pragma: no cover

    use_case = RestoreOnFirstRun(
        InMemorySetupGate(open=False),
        InMemoryBackupStore(),
        InMemoryDatabaseRestorer("revision"),
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        get_access_guard(),
    )
    with pytest.raises(RestoreTargetNotEmptyError):
        await use_case.handle(
            RestoreOnFirstRunCommand(stream=unreadable()), ANONYMOUS_ACTOR
        )


async def test_corrupt_upload_keeps_setup_empty() -> None:
    """A bad archive leaves the target empty and no committed upload behind."""
    store = InMemoryBackupStore()
    target = InMemoryDatabaseRestorer("revision")
    use_case = RestoreOnFirstRun(
        InMemorySetupGate(),
        store,
        target,
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        get_access_guard(),
    )
    with pytest.raises(CorruptBackupError):
        await use_case.handle(
            RestoreOnFirstRunCommand(stream=_chunks(b"broken")), ANONYMOUS_ACTOR
        )
    assert await target.is_empty()
    assert await store.list() == []

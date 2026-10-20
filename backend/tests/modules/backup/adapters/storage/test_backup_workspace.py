import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.adapters.storage.local_backup_workspace import (
    LocalBackupWorkspace,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


async def test_private_staging_streams_and_cleans_up(tmp_path: Path) -> None:
    """Stage bounded chunks on the backup volume and discard them."""
    workspace = LocalBackupWorkspace(tmp_path)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"one"
        yield b"two"

    key = await workspace.save(chunks())
    assert b"".join([chunk async for chunk in workspace.read(key)]) == b"onetwo"
    assert await workspace.open_archive(key) is not None
    await workspace.remove(key)
    assert list((tmp_path / ".staging").iterdir()) == []


async def test_failed_staging_removes_partial_file(tmp_path: Path) -> None:
    """A stream failure does not leave private partial bytes."""
    workspace = LocalBackupWorkspace(tmp_path)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"partial"
        raise OSError("input failed")

    with pytest.raises(OSError, match="input failed"):
        await workspace.save(chunks())
    assert list((tmp_path / ".staging").iterdir()) == []


async def test_prune_preserves_active_workspace_and_reaps_crashed_operation(
    tmp_path: Path,
) -> None:
    """The staging lease protects active uploads while abandoned bytes are prunable."""
    workspace, store = (
        LocalBackupWorkspace(tmp_path),
        LocalDirectoryBackupStore(tmp_path),
    )

    async def chunks() -> AsyncIterator[bytes]:
        yield b"private upload"

    key = await workspace.save(chunks())
    cutoff = datetime.now(UTC) + timedelta(days=1)
    assert await store.cleanup_orphans(before=cutoff, dry_run=False) == []
    assert b"".join([chunk async for chunk in workspace.read(key)]) == b"private upload"
    workspace._leases.pop(key).close()
    for path in (tmp_path / ".staging" / str(key)).iterdir():
        os.utime(path, (0, 0))
    os.utime(tmp_path / ".staging" / str(key), (0, 0))
    expected = str((tmp_path / ".staging" / str(key)).relative_to(tmp_path))
    assert await store.cleanup_orphans(before=cutoff, dry_run=True) == [expected]
    assert await store.cleanup_orphans(before=cutoff, dry_run=False) == [expected]
    await workspace.remove(key)
    assert list((tmp_path / ".staging").iterdir()) == []


async def test_failed_staging_lease_is_cleaned_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lease failure leaves no partial operation directory."""
    workspace = LocalBackupWorkspace(tmp_path)
    monkeypatch.setattr(
        "app.modules.backup.adapters.storage.local_backup_workspace.lock_staging",
        lambda path: None,
    )

    async def chunks() -> AsyncIterator[bytes]:
        yield b"unwritten"

    with pytest.raises(OSError, match="private staging lease"):
        await workspace.save(chunks())
    assert list((tmp_path / ".staging").iterdir()) == []

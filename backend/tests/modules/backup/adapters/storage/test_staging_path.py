"""`MENAGERIST_BACKUP_STAGING_PATH` moves restore and upload staging off the backups."""

import os
import sys
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.backup.adapters.storage.instance_storage import (
    STAGING_FOLDER,
    instance_store,
    instance_workspace,
)
from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.adapters.storage.local_backup_workspace import (
    LocalBackupWorkspace,
)
from app.modules.backup.adapters.storage.private_directory import (
    require_private_directory,
)
from app.modules.backup.domain.errors import BackupStorageError
from app.platform.config.backup import get_backup_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from pathlib import Path


async def _chunks() -> AsyncIterator[bytes]:
    yield b"staged"


def _age(path: Path) -> None:
    """Make `path` and everything in it look abandoned."""
    for entry in [path, *path.rglob("*")]:
        os.utime(entry, (1, 1))


async def test_a_workspace_stages_where_it_is_told_not_on_the_backup_volume(
    tmp_path: Path,
) -> None:
    """Staged bytes land in the chosen directory and nowhere on the backup volume."""
    backups, scratch = tmp_path / "backups", tmp_path / "scratch"
    workspace = LocalBackupWorkspace(backups, staging=scratch)

    key = await workspace.save(_chunks())

    assert b"".join([chunk async for chunk in workspace.read(key)]) == b"staged"
    assert (scratch / str(key)).is_dir()
    assert not backups.exists()
    await workspace.remove(key)
    assert list(scratch.iterdir()) == []


async def test_cleanup_reaches_abandoned_staging_outside_the_backup_volume(
    tmp_path: Path,
) -> None:
    """A crash mid-restore must not strand a copy of the media somewhere unswept."""
    backups, scratch = tmp_path / "backups", tmp_path / "scratch"
    stale, fresh = scratch / "stale", scratch / "fresh"
    scratch.mkdir(mode=0o700)
    for directory in (stale, fresh):
        directory.mkdir()
        (directory / "stream").write_bytes(b"bytes")
    _age(stale)
    store = LocalDirectoryBackupStore(backups, workspace_staging=scratch)
    before = datetime.now(UTC) - timedelta(hours=1)

    assert await store.cleanup_orphans(before=before, dry_run=True) == [str(stale)]
    assert stale.exists()
    assert await store.cleanup_orphans(before=before, dry_run=False) == [str(stale)]
    assert not stale.exists()
    assert fresh.exists()


async def test_a_store_without_outside_staging_ignores_other_directories(
    tmp_path: Path,
) -> None:
    """Without a configured staging path, clean-up looks only inside the volume."""
    other = tmp_path / "scratch" / "stale"
    other.mkdir(parents=True)
    _age(other)
    store = LocalDirectoryBackupStore(tmp_path / "backups")

    assert await store.cleanup_orphans(before=datetime.now(UTC), dry_run=False) == []
    assert other.exists()


@pytest.fixture
def backup_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the backup settings at a temporary volume; yield its path."""
    backups = tmp_path / "backups"
    monkeypatch.setenv("MENAGERIST_BACKUP_PATH", str(backups))
    monkeypatch.delenv("MENAGERIST_BACKUP_STAGING_PATH", raising=False)
    get_backup_settings.cache_clear()
    yield backups
    get_backup_settings.cache_clear()


async def test_staging_stays_in_the_backup_volume_by_default(
    backup_settings: Path,
) -> None:
    """Unset, staging is the `.staging` folder inside the backup volume."""
    key = await instance_workspace(get_backup_settings()).save(_chunks())

    assert (backup_settings / ".staging" / str(key)).is_dir()


async def test_a_configured_staging_path_gets_a_folder_of_its_own(
    backup_settings: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Menagerist writes and sweeps only its own folder inside the shared path."""
    shared = tmp_path / "shared-tmp"
    shared.mkdir()
    neighbour = shared / "someone-elses-cache"
    neighbour.mkdir()
    (neighbour / "data").write_bytes(b"keep me")
    _age(neighbour)
    monkeypatch.setenv("MENAGERIST_BACKUP_STAGING_PATH", str(shared))
    get_backup_settings.cache_clear()

    key = await instance_workspace(get_backup_settings()).save(_chunks())

    staged = shared / STAGING_FOLDER / str(key)
    assert staged.is_dir()
    assert not (backup_settings / ".staging").exists()
    _age(shared / STAGING_FOLDER)
    removed = await instance_store(get_backup_settings()).cleanup_orphans(
        before=datetime.now(UTC), dry_run=False
    )
    assert removed == [str(staged)]
    assert (neighbour / "data").read_bytes() == b"keep me"


async def test_a_symlinked_staging_folder_is_refused(tmp_path: Path) -> None:
    """A planted symlink must not redirect staged bytes somewhere else."""
    target = tmp_path / "elsewhere"
    target.mkdir()
    link = tmp_path / "scratch"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need privileges on this platform")
    workspace = LocalBackupWorkspace(tmp_path / "backups", staging=link)

    with pytest.raises(BackupStorageError):
        await workspace.save(_chunks())
    assert list(target.iterdir()) == []


async def test_cleanup_does_not_follow_a_symlink_in_staging(tmp_path: Path) -> None:
    """A link in the staging folder is left alone, and so is what it points at."""
    scratch, target = tmp_path / "scratch", tmp_path / "precious"
    scratch.mkdir()
    target.mkdir()
    (target / "data").write_bytes(b"keep")
    try:
        (scratch / "link").symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need privileges on this platform")
    _age(target)
    store = LocalDirectoryBackupStore(tmp_path / "backups", workspace_staging=scratch)

    assert await store.cleanup_orphans(before=datetime.now(UTC), dry_run=False) == []
    assert (target / "data").read_bytes() == b"keep"


async def test_cleanup_skips_a_staging_folder_that_is_a_link(tmp_path: Path) -> None:
    """A planted link in place of the folder is not swept, nor is its target."""
    target = tmp_path / "precious" / "stale"
    target.mkdir(parents=True)
    (target / "data").write_bytes(b"keep")
    _age(target)
    link = tmp_path / "scratch"
    try:
        link.symlink_to(target.parent, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need privileges on this platform")
    store = LocalDirectoryBackupStore(tmp_path / "backups", workspace_staging=link)

    assert await store.cleanup_orphans(before=datetime.now(UTC), dry_run=False) == []
    assert (target / "data").read_bytes() == b"keep"


def test_the_privacy_check_refuses_a_group_writable_folder(tmp_path: Path) -> None:
    """On POSIX, a folder other users can reach is not private."""
    if sys.platform == "win32":
        pytest.skip("POSIX permission bits")
    folder = tmp_path / "shared"
    folder.mkdir(mode=0o700)
    require_private_directory(folder)
    folder.chmod(0o770)
    with pytest.raises(OSError, match="not private"):
        require_private_directory(folder)

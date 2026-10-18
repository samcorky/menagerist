import asyncio
import shutil
from typing import TYPE_CHECKING

from app.modules.backup.adapters.storage.local_backup_reader import (
    CHUNK_SIZE,
    LocalBackupReader,
)
from app.modules.backup.adapters.storage.local_backup_writer import LocalBackupWriter
from app.modules.backup.adapters.storage.staging_lock import lock_staging
from app.modules.backup.application.archive import parse_summary
from app.modules.backup.domain.errors import (
    BackupNotFoundError,
    BackupStorageError,
    CorruptBackupError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import datetime
    from pathlib import Path
    from uuid import UUID

    from app.modules.backup.domain.backup import BackupSummary


class LocalDirectoryBackupStore:
    """Archives and commit-marker summaries on a local backup volume."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._instance = root / "instance"

    async def begin(self, backup_id: UUID) -> LocalBackupWriter:
        """Create private staging directories, reporting volume permissions."""

        def begin() -> LocalBackupWriter:
            self._instance.mkdir(parents=True, exist_ok=True)
            (self._root / ".staging").mkdir(mode=0o700, exist_ok=True)
            return LocalBackupWriter(self._root, backup_id)

        try:
            return await asyncio.to_thread(begin)
        except OSError as error:
            raise BackupStorageError(
                "Backup storage is unwritable; chown 1000:1000 <host directory>."
            ) from error

    def _require(self, backup_id: UUID) -> Path:
        path = self._instance / f"{backup_id}.tar.gz"
        if not (self._instance / f"{backup_id}.json").is_file() or not path.is_file():
            raise BackupNotFoundError(f"Backup {backup_id} was not found.")
        return path

    async def open(self, backup_id: UUID) -> LocalBackupReader:
        """Open a committed archive for sequential member reading."""
        return LocalBackupReader(await asyncio.to_thread(self._require, backup_id))

    async def read_bytes(self, backup_id: UUID) -> AsyncIterator[bytes]:
        """Download compressed bytes in bounded chunks."""
        path = await asyncio.to_thread(self._require, backup_id)
        stream = await asyncio.to_thread(path.open, "rb")
        try:
            while chunk := await asyncio.to_thread(stream.read, CHUNK_SIZE):
                yield chunk
        finally:
            await asyncio.to_thread(stream.close)

    async def archive_digest(self, backup_id: UUID) -> str | None:
        """Read the independent whole-archive SHA-256 sidecar."""
        await asyncio.to_thread(self._require, backup_id)
        path = self._instance / f"{backup_id}.sha256"
        try:
            fields = (await asyncio.to_thread(path.read_text)).split()
            return fields[0] if fields else None
        except FileNotFoundError:
            return None

    def _summaries(self) -> tuple[list[BackupSummary], list[str]]:
        summaries: list[BackupSummary] = []
        unreadable: list[str] = []
        for path in self._instance.glob("*.json"):
            try:
                summary = parse_summary(path.read_bytes())
                if path.stem != str(summary.id):
                    raise ValueError("Summary id differs from its filename.")
                summaries.append(summary)
            except OSError, ValueError, CorruptBackupError:
                unreadable.append(path.name)
        return summaries, unreadable

    async def unreadable(self) -> list[str]:
        """Report unreadable summary filenames while retaining their archives."""
        _, unreadable = await asyncio.to_thread(self._summaries)
        return unreadable

    async def delete(self, backup_id: UUID) -> None:
        """Remove summary first, then archive and optional sidecar."""
        await asyncio.to_thread(self._delete, backup_id)

    def _delete(self, backup_id: UUID) -> None:
        path = self._require(backup_id)
        (self._instance / f"{backup_id}.json").unlink()
        path.unlink()
        (self._instance / f"{backup_id}.sha256").unlink(missing_ok=True)

    async def cleanup_orphans(self, *, before: datetime, dry_run: bool) -> list[str]:
        """Remove uncommitted archives and stale staging operations."""
        return await asyncio.to_thread(self._cleanup, before, dry_run)

    def _orphan_archives(self) -> list[Path]:
        paths: list[Path] = []
        for path in self._instance.glob("*"):
            if path.name.endswith((".tar.gz", ".sha256")):
                stem = path.name.removesuffix(".tar.gz").removesuffix(".sha256")
                if (
                    self._inactive(self._root / ".staging" / stem)
                    and not (self._instance / f"{stem}.json").exists()
                ):
                    paths.append(path)
        return paths

    @staticmethod
    def _inactive(path: Path) -> bool:
        lock = path / ".lock"
        if not lock.exists():
            return True
        lease = lock_staging(lock)
        if lease is None:
            return False
        lease.close()
        return True

    def _stale_staging(self, before: datetime) -> list[Path]:
        paths: list[Path] = []
        for path in (self._root / ".staging").glob("*"):
            if not self._inactive(path):
                continue
            try:
                entries = [path, *path.rglob("*")] if path.is_dir() else [path]
                newest = max(entry.stat().st_mtime for entry in entries)
            except FileNotFoundError:
                continue
            if newest < before.timestamp():
                paths.append(path)
        return paths

    def _cleanup(self, before: datetime, dry_run: bool) -> list[str]:
        paths = self._orphan_archives() + self._stale_staging(before)
        if not dry_run:
            for path in paths:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
        return [str(path.relative_to(self._root)) for path in paths]

    async def list(self) -> list[BackupSummary]:
        """List valid commit markers without opening archives."""
        summaries, _ = await asyncio.to_thread(self._summaries)
        return summaries

import asyncio
import os
import shutil
import stat
import sys
from typing import TYPE_CHECKING
from uuid import UUID, uuid7

from app.modules.backup.adapters.storage.local_backup_reader import LocalBackupReader
from app.modules.backup.adapters.storage.staging_lock import lock_staging
from app.modules.backup.domain.errors import BackupStorageError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path
    from typing import BinaryIO


class LocalBackupWorkspace:
    """Stream private staging files into the configured backup volume."""

    def __init__(self, path: Path, staging: Path | None = None) -> None:
        """Stage under `staging`, or in `.staging` inside the backup volume `path`."""
        self._path = staging if staging is not None else path / ".staging"
        self._leases: dict[UUID, BinaryIO] = {}

    async def save(self, stream: AsyncIterator[bytes]) -> UUID:
        """Save a stream, removing partial output on failure."""
        key = uuid7()
        directory = self._path / str(key)

        def create_directory() -> None:
            self._path.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._require_private()
            directory.mkdir(mode=0o700)

        try:
            await asyncio.to_thread(create_directory)
        except OSError as error:
            raise BackupStorageError(
                "Backup storage is unwritable; chown 1000:1000 <host directory>."
            ) from error
        path = directory / "stream"
        file: BinaryIO | None = None
        try:
            lease = await asyncio.to_thread(lock_staging, directory / ".lock")
            if lease is None:
                raise OSError("Cannot acquire a private staging lease.")
            self._leases[key] = lease
            file = await asyncio.to_thread(path.open, "xb")
            await asyncio.to_thread(path.chmod, 0o600)
            async for chunk in stream:
                await asyncio.to_thread(file.write, chunk)
            await asyncio.to_thread(file.close)
        except BaseException:
            try:
                if file is not None:
                    await asyncio.to_thread(file.close)
            finally:
                await self.remove(key)
            raise
        return key

    def _require_private(self) -> None:
        """Refuse a staging folder someone else could have planted or can write to.

        It matters when the folder sits in a shared directory such as /tmp, where
        another user could pre-create the name as a symlink or a directory they own.
        """
        status = self._path.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise OSError("Staging path is not a real directory.")
        if sys.platform != "win32" and (
            status.st_uid != os.getuid() or status.st_mode & 0o077
        ):
            raise OSError("Staging path is not private to this user.")

    async def read(self, key: UUID) -> AsyncIterator[bytes]:
        """Read bounded chunks from a private file."""
        file = await asyncio.to_thread((self._path / str(key) / "stream").open, "rb")
        try:
            while chunk := await asyncio.to_thread(file.read, 1024 * 1024):
                yield chunk
        finally:
            await asyncio.to_thread(file.close)

    async def open_archive(self, key: UUID) -> LocalBackupReader:
        """Open staged compressed bytes without publishing them."""
        return LocalBackupReader(self._path / str(key) / "stream")

    async def remove(self, key: UUID) -> None:
        """Discard a staged file."""
        lease = self._leases.pop(key, None)
        if lease is not None:
            await asyncio.to_thread(lease.close)
        await asyncio.to_thread(
            shutil.rmtree, self._path / str(key), ignore_errors=True
        )

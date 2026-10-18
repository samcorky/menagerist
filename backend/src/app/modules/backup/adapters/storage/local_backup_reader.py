import asyncio
import gzip
import hashlib
import io
import tarfile
import zlib
from typing import IO, TYPE_CHECKING, BinaryIO

from app.modules.backup.domain.errors import CorruptBackupError
from app.modules.backup.ports.archive_member import ArchiveMember

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
    from pathlib import Path

CHUNK_SIZE = 1024 * 1024


class _HashingReader:
    def __init__(self, raw: BinaryIO) -> None:
        self.raw = raw
        self.digest = hashlib.sha256()

    def read(self, size: int = -1) -> bytes:
        data = self.raw.read(size)
        self.digest.update(data)
        return data

    def seek(self, offset: int, /) -> int:
        raise io.UnsupportedOperation("Backup archives are read sequentially.")


class LocalBackupReader:
    """Read each member once and hash the underlying compressed stream."""

    def __init__(self, source: Path | bytes) -> None:
        self._source = source
        self._digest: str | None = None

    async def members(self) -> AsyncGenerator[ArchiveMember]:
        """Yield regular files, validating gzip through its final trailer."""
        raw: BinaryIO = (
            io.BytesIO(self._source)
            if isinstance(self._source, bytes)
            else await asyncio.to_thread(self._source.open, "rb")
        )
        hashed = _HashingReader(raw)
        compressed = gzip.GzipFile(fileobj=hashed, mode="rb")
        archive: tarfile.TarFile | None = None
        try:
            archive = await asyncio.to_thread(
                tarfile.open, fileobj=compressed, mode="r|"
            )
            while (info := await asyncio.to_thread(archive.next)) is not None:
                if not info.isfile():
                    raise CorruptBackupError("Archives may contain only regular files.")
                stream = archive.extractfile(info)
                if stream is None:
                    raise CorruptBackupError("Archive member cannot be read.")
                try:
                    yield ArchiveMember(name=info.name, chunks=self._chunks(stream))
                    while await asyncio.to_thread(stream.read, CHUNK_SIZE):
                        pass
                finally:
                    await asyncio.to_thread(stream.close)
            while await asyncio.to_thread(compressed.read, CHUNK_SIZE):
                pass
            self._digest = hashed.digest.hexdigest()
        except (OSError, EOFError, tarfile.TarError, zlib.error) as error:
            raise CorruptBackupError(
                "The backup archive is damaged or truncated."
            ) from error
        finally:
            await asyncio.to_thread(self._complete, hashed, compressed, archive)

    def _complete(
        self,
        hashed: _HashingReader,
        compressed: gzip.GzipFile,
        archive: tarfile.TarFile | None,
    ) -> None:
        try:
            while hashed.read(CHUNK_SIZE):
                pass
        finally:
            self._digest = hashed.digest.hexdigest()
            if archive is not None:
                archive.close()
            compressed.close()
            hashed.raw.close()

    async def _chunks(self, stream: IO[bytes]) -> AsyncIterator[bytes]:
        try:
            while chunk := await asyncio.to_thread(stream.read, CHUNK_SIZE):
                yield chunk
        except (OSError, EOFError, tarfile.TarError, zlib.error) as error:
            raise CorruptBackupError(
                "The backup archive is damaged or truncated."
            ) from error

    async def archive_digest(self) -> str:
        """Return the compressed digest after the member stream is exhausted."""
        if self._digest is None:
            raise CorruptBackupError("The archive has not been completely read.")
        return self._digest

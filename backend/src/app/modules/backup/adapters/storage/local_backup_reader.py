import asyncio
import gzip
import hashlib
import io
import tarfile
import zlib
from contextvars import ContextVar
from typing import IO, TYPE_CHECKING, BinaryIO, Self

from app.modules.backup.domain.errors import CorruptBackupError
from app.modules.backup.ports.archive_member import ArchiveMember

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
    from pathlib import Path

CHUNK_SIZE = 1024 * 1024
MAX_EXTENSION_BYTES = 64 * 1024
_header_depth: ContextVar[int] = ContextVar("backup_tar_header_depth", default=0)


class _BoundedTarInfo(tarfile.TarInfo):
    """Bound metadata before the standard parser reads extension bodies."""

    @classmethod
    def frombuf(
        cls,
        buf: bytes | bytearray,
        encoding: str,
        errors: str,
    ) -> Self:
        """Validate header limits before extension bodies are read."""
        info = super().frombuf(buf, encoding, errors)
        if info.type == tarfile.GNUTYPE_SPARSE:
            raise CorruptBackupError("Sparse archive members are unsupported.")
        if (
            info.type
            in {
                tarfile.XHDTYPE,
                tarfile.XGLTYPE,
                tarfile.SOLARIS_XHDTYPE,
                tarfile.GNUTYPE_LONGNAME,
                tarfile.GNUTYPE_LONGLINK,
            }
            and not 0 <= info.size <= MAX_EXTENSION_BYTES
        ):
            raise CorruptBackupError(
                "Archive extension metadata exceeds its size limit."
            )
        return info

    @classmethod
    def fromtarfile(cls, archive: tarfile.TarFile) -> Self:
        """Bound recursive parsing of extension headers."""
        depth = _header_depth.get()
        if depth >= 16:
            raise CorruptBackupError("Archive extension metadata is nested too deeply.")
        token = _header_depth.set(depth + 1)
        try:
            return super().fromtarfile(archive)
        finally:
            _header_depth.reset(token)

    def _proc_gnusparse_00(
        self, next: tarfile.TarInfo, raw_headers: list[tuple[int, bytes, bytes]]
    ) -> None:
        raise CorruptBackupError("Sparse archive members are unsupported.")

    def _proc_gnusparse_01(
        self, next: tarfile.TarInfo, pax_headers: dict[str, str]
    ) -> None:
        raise CorruptBackupError("Sparse archive members are unsupported.")

    def _proc_gnusparse_10(
        self,
        next: tarfile.TarInfo,
        pax_headers: dict[str, str],
        archive: tarfile.TarFile,
    ) -> None:
        raise CorruptBackupError("Sparse archive members are unsupported.")


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
                tarfile.open, fileobj=compressed, mode="r|", tarinfo=_BoundedTarInfo
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

import asyncio
import gzip
import hashlib
import io
import os
import shutil
import tarfile
from typing import TYPE_CHECKING, BinaryIO
from uuid import UUID, uuid7

from app.modules.backup.adapters.storage.staging_lock import lock_staging
from app.modules.backup.application.archive import (
    checksum_bytes,
    manifest_bytes,
    summary_bytes,
    validate_member_name,
)
from app.modules.backup.domain.backup import (
    BackupManifest,
    BackupSummary,
    MemberDigest,
    StoredBackup,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


class _HashingWriter:
    def __init__(self, raw: BinaryIO) -> None:
        self.raw = raw
        self.digest = hashlib.sha256()

    def write(self, data: bytes) -> int:
        self.digest.update(data)
        return self.raw.write(data)

    def flush(self) -> None:
        self.raw.flush()


class LocalBackupWriter:
    """Spool one member at a time onto the backup volume before adding it."""

    def __init__(self, root: Path, backup_id: UUID) -> None:
        self._root = root
        self._id = backup_id
        self._staging = root / ".staging" / str(backup_id)
        self._staging.mkdir(mode=0o700)
        self._lease = lock_staging(self._staging / ".lock")
        self._partial = self._staging / f"{backup_id}.tar.gz.tmp"
        self._raw = self._partial.open("xb")
        self._partial.chmod(0o600)
        self._hashed = _HashingWriter(self._raw)
        self._gzip = gzip.GzipFile(
            fileobj=self._hashed, mode="wb", filename="", mtime=0
        )
        self._tar = tarfile.open(  # noqa: SIM115 - closed by finish() or abort().
            fileobj=self._gzip, mode="w|", format=tarfile.PAX_FORMAT
        )
        self._digests: dict[str, MemberDigest] = {}
        self._closed = False

    async def add(self, name: str, chunks: AsyncIterator[bytes]) -> MemberDigest:
        """Hash and spool member chunks without buffering a whole member."""
        validate_member_name(name)
        path = self._staging / f"{uuid7()}.member"
        digest = hashlib.sha256()
        size = lines = 0
        stream = await asyncio.to_thread(path.open, "xb")
        try:
            async for chunk in chunks:
                await asyncio.to_thread(stream.write, chunk)
                digest.update(chunk)
                size += len(chunk)
                lines += chunk.count(b"\n")
            await asyncio.to_thread(stream.close)
            await asyncio.to_thread(self._add_file, name, path, size)
        finally:
            await asyncio.to_thread(stream.close)
            await asyncio.to_thread(path.unlink, missing_ok=True)
        result = MemberDigest(size=size, sha256=digest.hexdigest(), lines=lines)
        self._digests[name] = result
        return result

    def _add_file(self, name: str, path: Path, size: int) -> None:
        info = tarfile.TarInfo(name)
        info.size = size
        info.mode = 0o600
        with path.open("rb") as stream:
            self._tar.addfile(info, stream)

    def _add_bytes(self, name: str, data: bytes) -> None:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o600
        self._tar.addfile(info, io.BytesIO(data))

    async def finish(self, manifest: BackupManifest) -> StoredBackup:
        """Publish archive, digest and finally its summary commit marker."""
        return await asyncio.to_thread(self._finish, manifest)

    def _finish(self, manifest: BackupManifest) -> StoredBackup:
        data = manifest_bytes(manifest)
        digests = self._digests | {
            "manifest.json": MemberDigest(
                size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                lines=data.count(b"\n"),
            )
        }
        self._add_bytes("checksums.sha256", checksum_bytes(digests))
        self._add_bytes("manifest.json", data)
        self._close()
        summary = BackupSummary(
            id=self._id,
            label=manifest.label,
            size=self._partial.stat().st_size,
            created_at=manifest.created_at,
            alembic_revision=manifest.alembic_revision,
            app_version=manifest.app_version,
        )
        destination = self._root / "instance" / str(self._id)
        self._partial.replace(destination.with_suffix(".tar.gz"))
        digest = self._hashed.digest.hexdigest()
        self._publish(
            destination.with_suffix(".sha256"),
            f"{digest}  {self._id}.tar.gz\n".encode(),
        )
        self._publish(destination.with_suffix(".json"), summary_bytes(summary))
        if self._lease is not None:
            self._lease.close()
        shutil.rmtree(self._staging)
        return StoredBackup(summary=summary, sha256=digest)

    def _publish(self, destination: Path, data: bytes) -> None:
        pending = self._staging / destination.name
        with pending.open("xb") as stream:
            pending.chmod(0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        pending.replace(destination)

    def _close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                try:
                    self._tar.close()
                finally:
                    self._gzip.close()
                self._raw.flush()
                os.fsync(self._raw.fileno())
            finally:
                self._raw.close()

    async def abort(self) -> None:
        """Remove unpublished files and release archive handles."""
        try:
            await asyncio.to_thread(self._close)
        finally:
            if self._lease is not None:
                self._lease.close()
            await asyncio.to_thread(shutil.rmtree, self._staging, ignore_errors=True)

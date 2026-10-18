import hashlib
import io
import json
import tarfile
from dataclasses import asdict
from typing import TYPE_CHECKING

from app.modules.backup.domain.backup import BackupSummary, MemberDigest, StoredBackup

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from app.modules.backup.domain.backup import BackupManifest


class InMemoryBackupWriter:
    """Buffer members and publish to shared dictionaries only on finish."""

    def __init__(
        self,
        backup_id: UUID,
        archives: dict[UUID, bytes],
        members: dict[UUID, dict[str, bytes]],
        summaries: dict[UUID, BackupSummary],
        digests: dict[UUID, str],
    ) -> None:
        self._id = backup_id
        self._archives = archives
        self._members = members
        self._summaries = summaries
        self._digests = digests
        self._pending: dict[str, bytes] = {}

    async def add(self, name: str, chunks: AsyncIterator[bytes]) -> MemberDigest:
        """Buffer a member and measure its uncompressed bytes."""
        data = b"".join([chunk async for chunk in chunks])
        self._pending[name] = data
        return MemberDigest(
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            lines=data.count(b"\n"),
        )

    async def finish(self, manifest: BackupManifest) -> StoredBackup:
        """Write a small real archive for download and digest tests."""
        manifest_bytes = json.dumps(asdict(manifest), default=str).encode()
        checksums = "".join(
            f"{hashlib.sha256(data).hexdigest()}  {name}\n"
            for name, data in (
                *self._pending.items(),
                ("manifest.json", manifest_bytes),
            )
        ).encode()
        self._pending["checksums.sha256"] = checksums
        self._pending["manifest.json"] = manifest_bytes
        output = io.BytesIO()
        with tarfile.open(
            fileobj=output, mode="w:gz", format=tarfile.PAX_FORMAT
        ) as archive:
            for name, data in self._pending.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        data = output.getvalue()
        summary = BackupSummary(
            id=self._id,
            label=manifest.label,
            size=len(data),
            created_at=manifest.created_at,
            alembic_revision=manifest.alembic_revision,
            app_version=manifest.app_version,
        )
        digest = hashlib.sha256(data).hexdigest()
        self._archives[self._id] = data
        self._members[self._id] = self._pending.copy()
        self._digests[self._id] = digest
        self._summaries[self._id] = summary
        return StoredBackup(summary=summary, sha256=digest)

    async def abort(self) -> None:
        """Discard unpublished members."""
        self._pending.clear()

import hashlib
from contextlib import aclosing
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.modules.backup.application.archive import analyse_members
from app.modules.backup.application.permissions import BackupPermission
from app.modules.backup.domain.backup import MemberDigest
from app.modules.backup.domain.errors import CorruptBackupError
from app.modules.backup.domain.verification import (
    Finding,
    FindingKind,
    VerificationReport,
)
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.backup.ports.archive_member import ArchiveMember
    from app.modules.backup.ports.backup_reader import BackupReader
    from app.modules.backup.ports.backup_store import BackupStore
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

_METADATA_LIMIT = 16 * 1024 * 1024


@dataclass(frozen=True, kw_only=True)
class VerifyBackupQuery:
    """Identify a committed archive to verify."""

    backup_id: UUID


async def _read_member(member: ArchiveMember) -> tuple[MemberDigest, bytes | None]:
    digest = hashlib.sha256()
    size = lines = 0
    collected = bytearray()
    is_metadata = member.name in {"manifest.json", "checksums.sha256"}
    async for chunk in member.chunks:
        digest.update(chunk)
        size += len(chunk)
        lines += chunk.count(b"\n")
        if is_metadata:
            if size > _METADATA_LIMIT:
                raise CorruptBackupError("Backup integrity metadata exceeds 16 MiB.")
            collected.extend(chunk)
    return MemberDigest(size=size, sha256=digest.hexdigest(), lines=lines), bytes(
        collected
    ) if is_metadata else None


async def _scan(
    reader: BackupReader,
) -> tuple[dict[str, MemberDigest], dict[str, bytes], list[Finding]]:
    digests: dict[str, MemberDigest] = {}
    metadata: dict[str, bytes] = {}
    findings: list[Finding] = []
    try:
        async with aclosing(reader.members()) as members:
            async for member in members:
                digest, data = await _read_member(member)
                if member.name in digests:
                    findings.append(
                        Finding(
                            kind=FindingKind.UNEXPECTED,
                            member=member.name,
                            actual="duplicate member",
                        )
                    )
                digests[member.name] = digest
                if data is not None:
                    metadata[member.name] = data
    except CorruptBackupError as exc:
        findings.append(
            Finding(
                kind=FindingKind.MANIFEST_INVALID, member="archive", actual=str(exc)
            )
        )
    return digests, metadata, findings


async def verify_archive(store: BackupStore, backup_id: UUID) -> VerificationReport:
    """Read compressed bytes once, checking every member and the digest sidecar."""
    reader = await store.open(backup_id)
    digests, metadata, findings = await _scan(reader)
    report = analyse_members(
        digests, metadata.get("manifest.json"), metadata.get("checksums.sha256")
    )
    findings.extend(report.findings)
    expected = await store.archive_digest(backup_id)
    try:
        actual = await reader.archive_digest()
    except CorruptBackupError as exc:
        findings.append(
            Finding(
                kind=FindingKind.MANIFEST_INVALID, member="archive", actual=str(exc)
            )
        )
    else:
        if expected != actual:
            findings.append(
                Finding(
                    kind=FindingKind.MISSING
                    if expected is None
                    else FindingKind.ARCHIVE_DIGEST_MISMATCH,
                    member=f"{backup_id}.tar.gz",
                    expected=expected,
                    actual=actual,
                )
            )
    return VerificationReport(findings=findings)


class VerifyBackup(UseCase[VerifyBackupQuery, VerificationReport]):
    """Verify integrity without turning findings into exceptions."""

    access: ClassVar[Access] = Requires(BackupPermission.READ)

    def __init__(self, store: BackupStore, guard: AccessGuard) -> None:
        self._guard = guard
        self._store = store

    async def _handle(
        self, request: VerifyBackupQuery, actor: Actor
    ) -> VerificationReport:
        return await verify_archive(self._store, request.backup_id)

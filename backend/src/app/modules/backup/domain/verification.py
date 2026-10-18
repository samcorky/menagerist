from dataclasses import dataclass, field
from enum import StrEnum


class FindingKind(StrEnum):
    """Integrity failures discovered during verification."""

    MISSING = "missing"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    UNEXPECTED = "unexpected"
    MANIFEST_INVALID = "manifest_invalid"
    ARCHIVE_DIGEST_MISMATCH = "archive_digest_mismatch"
    MEDIA_MISMATCH = "media_mismatch"


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One integrity failure with the expected and observed values."""

    kind: FindingKind
    member: str
    expected: str | None = None
    actual: str | None = None


@dataclass(frozen=True, kw_only=True)
class VerificationReport:
    """All findings from one archive verification."""

    findings: list[Finding] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PruneReport:
    """Retention decisions and storage reclaimed by pruning."""

    deleted: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    freed_bytes: int = 0
    orphans_removed: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
